import json
import time

import web

from jobserver.utils import get_ts
import jobserver.db as jdb
from jobserver.gitdb import config
from jobserver.webutils import abort, jsonify
from jobserver.build import create_session, get_session, get_build_info
from jobserver.build import set_session_done, set_session_running
from jobserver.build import SESSION_STATE_TO_BACKEND, SESSION_STATE_DONE
from jobserver.job import get_job, merge_job_parameters
from jobserver.queue import queue, DispatchSession, AgentAvailable
from jobserver.recipe import get_recipe_contents
from jobserver.slog import add_slog
from sci.slog import SessionStarted, SessionDone, RunAsync

urls = (
    '/available/A([0-9a-f]{40})', 'CheckInAvailable',
    '/busy/A([0-9a-f]{40})',      'CheckInBusy',
    '/dispatch',                  'DispatchBuild',
    '/agents',                    'GetAgentsInfo',
    '/queue',                     'GetQueueInfo',
    '/ping/A([0-9a-f]{40})',      'Ping',
    '/register',                  'Register',
    '/result/B([0-9a-f]{40})-([0-9]+)',    'GetSessionResult',
    '/session/(.+)',              'GetSessionInfo',
)

agent_app = web.application(urls, locals())


class Register:
    def POST(self):
        input = json.loads(web.data())
        db = jdb.conn()
        agent_id = input['id']

        info = {"ip": web.ctx.ip,
                'nick': input.get('nick', ''),
                "port": input["port"],
                "state": jdb.AGENT_STATE_INACTIVE,
                "seen": get_ts(),
                "labels": ",".join(input["labels"])}

        db.hmset(jdb.KEY_AGENT % agent_id, info)
        db.sadd(jdb.KEY_ALL, agent_id)

        for label in input["labels"]:
            db.sadd(jdb.KEY_LABEL % label, agent_id)

        return jsonify()


class CheckInAvailable:
    def POST(self, agent_id):
        agent_id = 'A' + agent_id
        db = jdb.conn()

        # Do we have results from a previous dispatch?
        data = json.loads(web.data())
        session_id = data.get('session_id')
        if session_id:
            set_session_done(db, session_id, data['result'], data['output'],
                             data['log_file'])
            add_slog(db, session_id, SessionDone(data['result']))

        db.hmset(jdb.KEY_AGENT % agent_id, dict(state = jdb.AGENT_STATE_AVAIL,
                                                seen = get_ts()))
        # To avoid race condition and slow computations, we let the backend
        # assign a new job to this slave, or set it as available.
        queue(db, AgentAvailable(agent_id))
        return jsonify()


class CheckInBusy:
    def POST(self, agent_id):
        agent_id = 'A' + agent_id
        db = jdb.conn()

        data = json.loads(web.data())
        session_id = data.get('id')
        if session_id:
            set_session_running(db, session_id)
            add_slog(db, session_id, SessionStarted())

        db.hmset(jdb.KEY_AGENT % agent_id, dict(state = jdb.AGENT_STATE_BUSY,
                                                seen = get_ts()))
        return jsonify()


class Ping:
    def POST(self, agent_id):
        agent_id = 'A' + agent_id
        db = jdb.conn()
        db.hset(jdb.KEY_AGENT % agent_id, 'seen', get_ts())
        return jsonify()


class DispatchBuild:
    def POST(self):
        db = jdb.conn()
        input = json.loads(web.data())
        session_no = create_session(db, input['build_id'],
                                    parent = input['parent'],
                                    labels = input['labels'],
                                    run_info = input['run_info'],
                                    state = SESSION_STATE_TO_BACKEND)
        session_id = '%s-%s' % (input['build_id'], session_no)
        item = RunAsync(session_no, input['run_info']['step_name'],
                        input['run_info']['args'], input['run_info']['kwargs'])
        add_slog(db, input['parent'], item)
        queue(db, DispatchSession(session_id))
        return jsonify(session_id = session_id)


class GetSessionResult:
    def GET(self, build_id, session_no):
        session_id = 'B%s-%s' % (build_id, session_no)
        db = jdb.conn()
        while True:
            info = get_session(db, session_id)
            if not info:
                abort(404, "Session ID not found")
            if info['state'] == SESSION_STATE_DONE:
                return jsonify(result = info['result'],
                               output = info['output'])
            time.sleep(0.5)


class GetSessionInfo:
    def GET(self, session_id):
        db = jdb.conn()
        repo = config()
        session = get_session(db, session_id)
        build_uuid = session_id.split('-')[0]
        build = get_build_info(db, build_uuid)
        ref, recipe = get_recipe_contents(repo, build['recipe'],
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
                       ss_token = build['ss_token'],
                       ss_url = web.config._ss_url,
                       parameters = parameters)


class GetAgentsInfo:
    def GET(self):
        db = jdb.conn()
        all = []
        for agent_id in db.smembers(jdb.KEY_ALL):
            info = db.hgetall(jdb.KEY_AGENT % agent_id)
            if info:
                all.append({'id': agent_id,
                            'nick': info.get('nick', ''),
                            "state": info["state"],
                            "seen": int(info["seen"]),
                            "labels": info["labels"].split(",")})
        return jsonify(agent_no = len(all),
                       agents = all)


class GetQueueInfo:
    def GET(self):
        db = jdb.conn()
        queue = []
        for did in db.zrange(jdb.KEY_QUEUE, 0, -1):
            info = db.get(jdb.KEY_DISPATCH_INFO % did)
            if info:
                info = json.loads(info)
                queue.append({"id": did,
                              "labels": info["labels"]})
        return jsonify(queue = queue)
