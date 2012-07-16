import json
import time

from flask import Blueprint, request, abort, jsonify, current_app, g
from pyres import ResQ

from jobserver.utils import get_ts
import jobserver.db as jdb
from jobserver.build import create_session, get_session, get_build_info
from jobserver.build import set_session_done, set_session_running
from jobserver.build import get_session_title, set_build_done
from jobserver.build import SESSION_STATE_TO_BACKEND, SESSION_STATE_DONE
from jobserver.job import Job
from jobserver.recipe import Recipe
from jobserver.slog import add_slog
from async.agent_available import AgentAvailable
from async.dispatch_session import DispatchSession
from jobserver.utils import chunks

app = Blueprint('agents', __name__)

AGENT_HISTORY_LIMIT = 100


class LogItem(object):
    def __init__(self):
        self.params = {}

    def serialize(self):
        d = dict(type = self.type)
        if self.params:
            d['params'] = self.params
        return json.dumps(d)


class SessionStarted(LogItem):
    type = 'session-start'


class SessionDone(LogItem):
    type = 'session-done'

    def __init__(self, result):
        self.params = dict(result = result)


class RunAsync(LogItem):
    type = 'run-async'

    def __init__(self, session_no, title):
        self.params = dict(session_no = int(session_no),
                           title = title)


def add_to_history(pipe, agent_id, session_id):
    pipe.lpush(jdb.KEY_AGENT_HISTORY % agent_id, session_id)
    pipe.ltrim(jdb.KEY_AGENT_HISTORY % agent_id, 0, AGENT_HISTORY_LIMIT - 1)


@app.route('/register', methods=['POST'])
def do_register():
    agent_id = request.json['id']

    info = {"ip": request.remote_addr,
            'nick': request.json.get('nick', ''),
            "port": request.json["port"],
            "state": jdb.AGENT_STATE_AVAIL,
            "seen": get_ts(),
            "labels": ",".join(request.json["labels"])}

    with g.db.pipeline() as pipe:
        pipe.hmset(jdb.KEY_AGENT % agent_id, info)
        pipe.sadd(jdb.KEY_ALL, agent_id)

        for label in request.json["labels"]:
            pipe.sadd(jdb.KEY_LABEL % label, agent_id)
        pipe.execute()

    r = ResQ()
    r.enqueue(AgentAvailable, agent_id)
    return jsonify()


@app.route('/available/<agent_id>', methods=['POST'])
def check_in_available(agent_id):
    session_id = request.json['session_id']
    build_id, num = session_id.split('-')
    with g.db.pipeline() as pipe:
        set_session_done(pipe, session_id, request.json['result'],
                         request.json['output'], request.json['log_file'])
        if int(num) == 0:
            set_build_done(pipe, build_id, request.json['result'])

        add_slog(pipe, session_id, SessionDone(request.json['result']))

        pipe.hmset(jdb.KEY_AGENT % agent_id, dict(state = jdb.AGENT_STATE_AVAIL,
                                                  seen = get_ts()))
        pipe.execute()

    r = ResQ()
    r.enqueue(AgentAvailable, agent_id)
    return jsonify()


@app.route('/busy/<agent_id>', methods=['POST'])
def check_in_busy(agent_id):
    with g.db.pipeline() as pipe:
        session_id = request.json['session_id']
        set_session_running(pipe, session_id)
        add_slog(pipe, session_id, SessionStarted())
        add_to_history(pipe, agent_id, session_id)

        pipe.hmset(jdb.KEY_AGENT % agent_id, dict(state = jdb.AGENT_STATE_BUSY,
                                                  seen = get_ts()))
        pipe.execute()
    return jsonify()


@app.route('/ping/<agent_id>', methods=['POST'])
def ping(agent_id):
    g.db.hset(jdb.KEY_AGENT % agent_id, 'seen', get_ts())
    return jsonify()


@app.route('/dispatch', methods=['POST'])
def dispatch():
    input = request.json
    session_no = create_session(g.db, input['build_id'],
                                parent = input['parent'],
                                labels = input['labels'],
                                run_info = input['run_info'],
                                state = SESSION_STATE_TO_BACKEND)
    session_id = '%s-%s' % (input['build_id'], session_no)
    ri = input['run_info'] or {}
    args = ", ".join(ri.get('args', []))
    title = "%s(%s)" % (ri.get('step_name', 'main'), args)
    item = RunAsync(session_no, title)
    add_slog(g.db, input['parent'], item)
    r = ResQ()
    r.enqueue(DispatchSession, session_id)
    return jsonify(session_id = session_id)


@app.route('/result/<session_id>', methods=['GET'])
def get_session_result(session_id):
    while True:
        info = get_session(g.db, session_id)
        if not info:
            abort(404, "Session ID not found")
        if info['state'] == SESSION_STATE_DONE:
            return jsonify(result = info['result'],
                           output = info['output'])
        time.sleep(0.5)


@app.route('/session/<session_id>')
def get_session_info(session_id):
    session = get_session(g.db, session_id)
    build_uuid = session_id.split('-')[0]
    build = get_build_info(g.db, build_uuid)
    recipe = Recipe.load(build['recipe'], build['recipe_ref'])
    job = Job.load(build['job_name'], build['job_ref'])

    # Calculate the actual parameters - setting defaults if static value.
    # (parameters that have a function as default value will have them
    #  called just before starting the job)
    param_def = job.get_merged_params()
    parameters = build['parameters']

    for name in param_def:
        param = param_def[name]
        if 'default' in param and not name in parameters:
            parameters[name] = param['default']

    return jsonify(run_info = session['run_info'] or {},
                   build_uuid = build_uuid,
                   build_name = "%s-%d" % (build['job_name'], build['number']),
                   recipe = recipe.contents,
                   ss_token = build['ss_token'],
                   ss_url = current_app.config['SS_URL'],
                   parameters = parameters)


@app.route('/list')
def list_agents():
    fields = ('#', 'agent:info:*->nick', 'agent:info:*->state',
              'agent:info:*->seen', 'agent:info:*->labels')
    all = [{'id': d[0], 'nick': d[1], 'state': d[2], 'seen': int(d[3]),
            'labels': [t for t in d[4].split(',') if t]}
            for d in chunks(g.db.sort(jdb.KEY_ALL, get=fields), 5)]
    return jsonify(agent_no = len(all),
                   agents = all)


@app.route('/queue')
def list_queue():
    queue = []
    for did in g.db.zrange(jdb.KEY_QUEUE, 0, -1):
        info = g.db.get(jdb.KEY_DISPATCH_INFO % did)
        if info:
            info = json.loads(info)
            queue.append({"id": did,
                          "labels": info["labels"]})
    return jsonify(queue = queue)


@app.route('/details/<agent_id>')
def agent_details(agent_id):
    info = g.db.hgetall(jdb.KEY_AGENT % agent_id)
    if not info:
        abort(404)
    history = []
    for session_id in g.db.lrange(jdb.KEY_AGENT_HISTORY % agent_id, 0, 19):
        build_id = session_id.split('-')[0]
        build = get_build_info(g.db, build_id)
        session = get_session(g.db, session_id)
        history.append({'session_id': session_id,
                        'build_id': build['build_id'],
                        'job_name': build['job_name'],
                        'number': build['number'],
                        'started': session['started'],
                        'ended': session['ended'],
                        'result': session['result'],
                        'title': get_session_title(session)})

    return jsonify(id = agent_id,
                   nick = info.get('nick', ''),
                   state = info["state"],
                   seen = int(info["seen"]),
                   labels = info["labels"].split(","),
                   history = history)
