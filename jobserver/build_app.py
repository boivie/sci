import json

import web

from jobserver.slog import KEY_SLOG
from jobserver.db import conn
from jobserver.webutils import abort, jsonify
from jobserver.gitdb import config
from jobserver.job import get_job
from jobserver.build import new_build, get_build_info, set_session_running
from jobserver.build import set_session_done, get_session
from jobserver.build import KEY_JOB_BUILDS, set_session_queued
from jobserver.queue import queue, DispatchSession

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
)

build_app = web.application(urls, locals())


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
        set_session_done(db, 'B%s-1' % build_id, input['result'], input['output'], None)
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
        log = [json.loads(l) for l in log]
        # Fetch information about all sessions
        sessions = []
        for i in range(1, int(build['max_session']) + 1):
            s = get_session(db, '%s-%d' % (build_id, i))
            ri = s['run_info'] or {}
            args = ", ".join(ri.get('args', []))
            title = "%s(%s)" % (ri.get('step_name', 'main'), args)
            sessions.append({'num': i,
                             'agent': s['agent'],
                             'title': title,
                             'log_file': s['log_file'],
                             'parent': s['parent'],
                             'state': s['state'],
                             'result': s['result']})
        return jsonify(build = build,
                       log = log,
                       sessions = sessions)
