import json

import web

from jobserver.slog import KEY_SLOG, KEY_BUILD_SESSIONS
from jobserver.db import conn
from jobserver.webutils import abort, jsonify
from jobserver.gitdb import config
from jobserver.job import get_job
from jobserver.build import new_build, get_build_info, STATE_QUEUED
from jobserver.build import KEY_JOB_BUILDS
from jobserver.queue import queue, StartBuildQ

urls = (
    '/create/(.+).json',     'CreateBuild',
    '/start/(.+)',           'StartBuild',

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
        build_id, build = new_build(db, job, job_ref,
                                    input.get('parameters', {}))

        return jsonify(id = build_id, **build)


class StartBuild:
    def POST(self, job_name):
        db = conn()
        repo = config()
        data = web.data()
        input = json.loads(data) if data else {}

        job, job_ref = get_job(repo, job_name, input.get('job_ref'))
        build_id, build = new_build(db, job, job_ref,
                                    input.get('parameters', {}),
                                    state = STATE_QUEUED)

        queue(db, StartBuildQ(build_id, build['session_id']))
        return jsonify(id = build_id, **build)


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

        log = {}
        sessions = db.smembers(KEY_BUILD_SESSIONS % build_id)
        for session_id in sessions:
            log[session_id] = db.lrange(KEY_SLOG % (build_id, session_id),
                                        0, 1000)
        return jsonify(build = build,
                       log = log)
