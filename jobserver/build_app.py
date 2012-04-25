import json
from flask import Blueprint, request, abort, jsonify

from jobserver.slog import KEY_SLOG
from jobserver.db import conn
from jobserver.gitdb import config
from jobserver.job import get_job
from jobserver.build import new_build, get_build_info, set_session_running
from jobserver.build import set_session_done, get_session
from jobserver.build import KEY_JOB_BUILDS, set_session_queued
from jobserver.queue import queue, DispatchSession

app = Blueprint('build', __name__)


@app.route('/create/<job_name>.json', methods=['POST'])
def do_create_build(job_name):
    db = conn()
    repo = config()
    input = request.json

    job, job_ref = get_job(repo, job_name, input.get('job_ref'))
    build = new_build(db, job, job_ref,
                      parameters = input.get('parameters', {}),
                      description = input.get('description', ''))

    return jsonify(**build)


@app.route('/start/<job_name>', methods=['POST'])
def do_start_build(job_name):
    db = conn()
    repo = config()
    input = request.json

    job, job_ref = get_job(repo, job_name, input.get('job_ref'))
    build = new_build(db, job, job_ref,
                      parameters = input.get('parameters', {}),
                      description = input.get('description', ''))
    set_session_queued(db, build['session_id'])
    queue(db, DispatchSession(build['session_id']))
    return jsonify(**build)


@app.route('/started/<build_id>', methods=['POST'])
def set_started_build(build_id):
    db = conn()
    set_session_running(db, "%s-0" % build_id)
    return jsonify()


@app.route('/done/<build_id>', methods=['POST'])
def set_done_build(build_id):
    set_session_done(conn(), "%s-0" % build_id, request.json['result'],
                     request.json['output'], None)
    return jsonify()


@app.route('/<build_id>.json', methods=['GET'])
def get_build(build_id):
    build = get_build_info(conn(), build_id)
    if not build:
        abort(404, 'Invalid Build ID')
    return jsonify(build = build)


@app.route('/<job_name>,<number>', methods=['GET'])
def get_build2(job_name, number):
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
    for i in range(int(build['next_sess_id'])):
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
