import json
from flask import Blueprint, request, abort, jsonify, g
from pyres import ResQ

from jobserver.slog import KEY_SLOG
from jobserver.db import KEY_AGENT
from jobserver.job import get_job
from jobserver.build import new_build, get_build_info, set_session_running
from jobserver.build import set_session_done, get_session, get_session_title
from jobserver.build import KEY_JOB_BUILDS, set_session_queued
from async.dispatch_session import DispatchSession

app = Blueprint('build', __name__)


@app.route('/create/<job_name>.json', methods=['POST'])
def do_create_build(job_name):
    input = request.json

    job, job_ref = get_job(g.db, job_name, input.get('job_ref'))
    build = new_build(job, job_ref,
                      parameters = input.get('parameters', {}),
                      description = input.get('description', ''))

    return jsonify(**build)


@app.route('/start/<job_name>', methods=['POST'])
def do_start_build(job_name):
    input = request.json

    job, job_ref = get_job(g.db, job_name, input.get('job_ref'))
    build = new_build(job, job_ref,
                      parameters = input.get('parameters', {}),
                      description = input.get('description', ''))
    session_id = '%s-0' % build['uuid']
    set_session_queued(g.db, session_id)
    r = ResQ()
    r.enqueue(DispatchSession, session_id)
    return jsonify(**build)


@app.route('/started/<build_id>', methods=['POST'])
def set_started_build(build_id):
    set_session_running(g.db, "%s-0" % build_id)
    return jsonify()


@app.route('/done/<build_id>', methods=['POST'])
def set_done_build(build_id):
    set_session_done(g.db, "%s-0" % build_id, request.json['result'],
                     request.json['output'], None)
    return jsonify()


@app.route('/<build_id>.json', methods=['GET'])
def get_build(build_id):
    build = get_build_info(g.db, build_id)
    if not build:
        abort(404, 'Invalid Build ID')
    return jsonify(build = build)


@app.route('/<job_name>,<number>', methods=['GET'])
def get_build2(job_name, number):
    number = int(number)
    build_id = g.db.lindex(KEY_JOB_BUILDS % job_name, number - 1)
    if build_id is None:
        abort(404, 'Not Found')
    build = get_build_info(g.db, build_id)
    if not build:
        abort(404, 'Invalid Build ID')

    log = g.db.lrange(KEY_SLOG % build_id, 0, 1000)
    log = [json.loads(l) for l in log]
    # Fetch information about all sessions
    sessions = []
    for i in range(int(build['next_sess_id'])):
        s = get_session(g.db, '%s-%d' % (build_id, i))
        sessions.append({'num': i,
                         'agent_id': s['agent'],
                         'agent_nick': '',
                         'title': get_session_title(s),
                         'log_file': s['log_file'],
                         'parent': s['parent'],
                         'state': s['state'],
                         'result': s['result']})

    # Fetch info about the agents (the nick name)
    agents = set([s['agent_id'] for s in sessions])
    for agent_id in agents:
        nick = g.db.hget(KEY_AGENT % agent_id, 'nick')
        for s in sessions:
            if s['agent_id'] == agent_id:
                s['agent_nick'] = nick

    return jsonify(build = build,
                   log = log,
                   sessions = sessions)
