import json

import web

from jobserver.slog import KEY_SLOG
from jobserver.db import conn
from jobserver.webutils import abort, jsonify
from jobserver.gitdb import config
from jobserver.job import get_job, merge_job_parameters
from jobserver.build import new_build, get_build_info, set_session_running
from jobserver.build import set_session_done, get_session
from jobserver.build import KEY_JOB_BUILDS, set_session_queued
from jobserver.queue import queue, DispatchSession
from jobserver.recipe import get_recipe_contents

urls = (
    '/create/(.+).json',     'CreateBuild',
    '/start/(.+)',           'StartBuild',

    # Used when manually testing a job
    '/started/B([0-9a-f]{40})',         'StartedBuild',
    '/done/B([0-9a-f]{40})',            'DoneBuild',

    # If the build ID is specified, we allow it to be updated
    '/B([0-9a-f]{40}).json', 'GetUpdateBuild',
    # If only the name+number is specified, read-only access
    '/(.+),([0-9]+)',        'GetBuild',
    # Used only by the agent when fetching the session information
    '/session/(.+)', 'GetSession',
)

build_app = web.application(urls, locals())


class GetSession:
    def GET(self, session_id):
        db = conn()
        repo = config()
        session = get_session(db, session_id)
        build_uuid = session_id.split('-')[0]
        build = get_build_info(db, build_uuid)
        ref, recipe = get_recipe_contents(repo, build['recipe_name'],
                                          build.get('recipe_ref'))
        job, ref = get_job(repo, build['job_name'], build.get('job_ref'))

        # Calculate the actual parameters - setting defaults if static value.
        # (parameters that have a function as default value will have them
        #  called just before starting the job)
        param_def = merge_job_parameters(repo, job)
        parameters = build['parameters']

        for name in param_def:
            param = param_def[name]
            if 'default' in param and not name in parameters:
                parameters[name] = param['default']

        return jsonify(run_info = session['run_info'] or {},
                       build_uuid = build_uuid,
                       build_name = "%s-%d" % (build['job_name'], build['number']),
                       recipe = recipe,
                       parameters = parameters)


class CreateBuild:
    def POST(self, job_name):
        db = conn()
        repo = config()
        data = web.data()
        input = json.loads(data) if data else {}

        job, job_ref = get_job(repo, job_name, input.get('job_ref'))
        build = new_build(db, job, job_ref,
                          parameters = input.get('parameters', {}),
                          description = input.get('description', ''))

        return jsonify(**build)


class StartBuild:
    def POST(self, job_name):
        db = conn()
        repo = config()
        data = web.data()
        input = json.loads(data) if data else {}

        job, job_ref = get_job(repo, job_name, input.get('job_ref'))
        build = new_build(db, job, job_ref,
                          parameters = input.get('parameters', {}),
                          description = input.get('description', ''))
        set_session_queued(db, build['session_id'])
        queue(db, DispatchSession(build['session_id']))
        return jsonify(**build)


class StartedBuild:
    def POST(self, build_id):
        db = conn()
        set_session_running(db, 'B%s-1' % build_id)
        return jsonify()


class DoneBuild:
    def POST(self, build_id):
        db = conn()
        input = json.loads(web.data())
        set_session_done(db, 'B%s-1' % build_id, input['result'], input['output'])
        return jsonify()


class GetUpdateBuild:
    def GET(self, build_id):
        build = get_build_info(conn(), 'B' + build_id)
        if not build:
            abort(404, 'Invalid Build ID')
        return jsonify(build = build)


class GetBuild:
    def GET(self, job_name, number):
        db = conn()
        number = int(number)
        build_id = db.lindex(KEY_JOB_BUILDS % job_name, number - 1)
        if build_id is None:
            abort(404, 'Not Found')
        build = get_build_info(db, build_id)
        if not build:
            abort(404, 'Invalid Build ID')

        log = db.lrange(KEY_SLOG % build_id, 0, 1000)
        # Fetch state and result for the main session also
        session = get_session(db, build_id + '-1')
        build['state'] = session['state']
        build['result'] = session['result']
        return jsonify(build = build,
                       log = log)
