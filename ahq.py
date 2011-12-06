#!/usr/bin/env python
"""
    sci.ahq
    ~~~~~~~

    Agent Coordinator

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
from optparse import OptionParser
import web, redis, json, time, logging
from sci.utils import random_sha1
from sci.http_client import HttpClient


KEY_LABEL = 'ahq:label:%s'
KEY_AGENT = 'agent:info:%s'
KEY_TOKEN = 'ahq:token:%s'
KEY_ALLOCATION = "ahq:alloc:%s"
KEY_DISPATCH_INFO = 'ahq:dispatch:info:%s'
KEY_QUEUE = 'ahq:dispatchq'

KEY_ALL = 'agents:all'
KEY_AVAILABLE = 'agents:avail'

ALLOCATION_EXPIRY_TTL = 1 * 60
SEEN_EXPIRY_TTL = 2 * 60

STATE_INACTIVE = "inactive"
STATE_AVAIL = "available"
STATE_PENDING = "pending"
STATE_BUSY = "busy"

DISPATCH_STATE_QUEUED = 'queued'
DISPATCH_STATE_RUNNING = 'running'
DISPATCH_STATE_DONE = 'done'

urls = (
    '/A([0-9a-f]{40})/register.json',  'Register',
    '/N([0-9a-f]{40})/available.json', 'CheckInAvailable',
    '/N([0-9a-f]{40})/busy.json',      'CheckInBusy',
    '/N([0-9a-f]{40})/ping.json',      'Ping',
    '/dispatch',                       'DispatchBuild',
    '/S([0-9a-f]{40})/result',    'GetDispatchedResult',
    '/info.json',                      'GetInfo'
)

app = web.application(urls, globals())
pool = redis.ConnectionPool(host='localhost', port=6379, db=0)


def get_ts():
    return int(time.time())


def jsonify(**kwargs):
    web.header('Content-Type', 'application/json')
    return json.dumps(kwargs)


def abort(status, data):
    raise web.webapi.HTTPError(status = status, data = data)


def conn():
    r = redis.StrictRedis(connection_pool=pool)
    return r


class Register:
    def POST(self, agent_id):
        input = json.loads(web.data())
        db = conn()
        token_id = random_sha1()
        old_info = db.get(KEY_AGENT % agent_id)
        if old_info:
            old_info = json.loads(old_info)
        else:
            old_info = {}

        info = {"ip": web.ctx.ip,
                "port": input["port"],
                "state": STATE_INACTIVE,
                "token_id": token_id,
                "seen": get_ts(),
                "labels": input["labels"]}

        db.set(KEY_AGENT % agent_id, json.dumps(info))
        db.sadd(KEY_ALL, agent_id)

        for label in input["labels"]:
            db.sadd(KEY_LABEL % label, agent_id)

        db.set(KEY_TOKEN % token_id, agent_id)
        return jsonify(token = 'N' + token_id)


def get_did_or_make_avail(pipe, agent_id, agent_info):
    """Starts multi, doesn't exec"""
    pipe.watch(KEY_QUEUE)
    queue = pipe.zrange(KEY_QUEUE, 0, -1)
    for session_id in queue:
        dispatch_info = json.loads(pipe.get(KEY_DISPATCH_INFO % session_id))
        # Do we fulfill its requirements?
        if dispatch_info['state'] != DISPATCH_STATE_QUEUED:
            continue
        if not set(dispatch_info["labels"]).issubset(set(agent_info["labels"])):
            continue
        # Yup. Use it.
        agent_info["state"] = STATE_PENDING
        pipe.multi()
        pipe.zrem(KEY_QUEUE, session_id)
        return dispatch_info['data']
    # Nope. None matching -> put it as available.
    pipe.multi()
    agent_info["state"] = STATE_AVAIL
    pipe.sadd(KEY_AVAILABLE, agent_id)
    return None


def handle_last_results(db, agent_id, data):
    data = json.loads(data)
    session_id = data.get('id')
    result = data.get('result')
    if not session_id:
        return
    key = KEY_DISPATCH_INFO % session_id
    while True:
        try:
            with db.pipeline() as pipe:
                pipe.watch(key)
                info = json.loads(pipe.get(key))
                info['state'] = DISPATCH_STATE_DONE
                info['result'] = result
                pipe.multi()
                pipe.set(key, json.dumps(info))
                pipe.execute()
                break
        except redis.WatchError:
            continue


class CheckInAvailable:
    def POST(self, token_id):
        now = get_ts()
        db = conn()

        agent_id = db.get(KEY_TOKEN % token_id)
        if agent_id is None:
            abort(404, "Invalid token")

        # Do we have results from a previous dispatch?
        handle_last_results(db, agent_id, web.data())

        while True:
            try:
                with db.pipeline() as pipe:
                    dinfo = None
                    pipe.watch(KEY_AGENT % agent_id)
                    info = json.loads(pipe.get(KEY_AGENT % agent_id))

                    dinfo = get_did_or_make_avail(pipe, agent_id, info)
                    info['seen'] = now
                    info['state'] = STATE_AVAIL
                    pipe.set(KEY_AGENT % agent_id, json.dumps(info))
                    pipe.execute()
                    # We succeeded!
                    if dinfo:
                        session_id = dinfo['session_id']
                        logging.debug("A%s checked in -> D%s" % (agent_id,
                                                                 session_id))
                        return jsonify(do = json.dumps(dinfo))
                    else:
                        logging.debug("A%s checked in" % agent_id)
                        return jsonify()
                    break
            except redis.WatchError:
                continue


class CheckInBusy:
    def POST(self, token_id):
        now = get_ts()
        db = conn()

        agent_id = db.get(KEY_TOKEN % token_id)
        if agent_id is None:
            abort(404, "Invalid token")

        while True:
            try:
                with db.pipeline() as pipe:
                    pipe.watch(KEY_AGENT % agent_id)
                    info = json.loads(pipe.get(KEY_AGENT % agent_id))
                    pipe.multi()
                    info["seen"] = now
                    info["state"] = STATE_BUSY
                    pipe.set(KEY_AGENT % agent_id, json.dumps(info))
                    pipe.execute()
                    break
            except redis.WatchError:
                continue
        return jsonify()


class Ping:
    def POST(self, token_id):
        db = conn()
        agent_id = db.get(KEY_TOKEN % token_id)
        if agent_id is None:
            abort(404, "Invalid token")

        while True:
            try:
                with db.pipeline() as pipe:
                    pipe.watch(KEY_AGENT % agent_id)
                    info = json.loads(pipe.get(KEY_AGENT % agent_id))

                    info["seen"] = get_ts()
                    pipe.multi()
                    pipe.set(KEY_AGENT % agent_id, json.dumps(info))
                    pipe.execute()
                    break
            except redis.WatchError:
                continue

        return jsonify(status = "ok")


def allocate(pipe, agent_id, session_id):
    """Starts multi, doesn't exec"""
    pipe.watch(KEY_AGENT % agent_id)
    info = json.loads(pipe.get(KEY_AGENT % agent_id))

    pipe.multi()
    pipe.srem(KEY_AVAILABLE, agent_id)
    if info["state"] != STATE_AVAIL:
        return None

    # verify the 'seen' so that it's not too old
    if info["seen"] + SEEN_EXPIRY_TTL < int(time.time()):
        print("A%s didn't check in - dropping" % agent_id)
        info["state"] = STATE_INACTIVE
        pipe.set(KEY_AGENT % agent_id, json.dumps(info))
        return None

    info["state"] = STATE_PENDING
    info['dispatch_id'] = session_id
    pipe.set(KEY_AGENT % agent_id, json.dumps(info))
    return info


def dispatch_later(pipe, input):
    """Starts multi, doesn't exec"""
    session_id = input['session_id']
    pipe.multi()
    pipe.set(KEY_DISPATCH_INFO % session_id,
             json.dumps({'labels': input['labels'],
                         'data': input,
                         'state': DISPATCH_STATE_QUEUED}))
    ts = float(time.time() * 1000)
    pipe.zadd(KEY_QUEUE, ts, session_id)
    return session_id


def do_dispatch(db, agent_id, agent_url, input):
    print("AGENT URL: '%s'" % agent_url)
    client = HttpClient(agent_url)
    client.call('/dispatch', input = json.dumps(input))
    # TODO: Possible race condition: The client may finish here,
    # and call 'checkin'.
    db.set(KEY_DISPATCH_INFO % input['session_id'],
           json.dumps({'agent_id': agent_id,
                       'state': DISPATCH_STATE_RUNNING}))


def report_to_jobserver(job_server, build_id, parent_session,
                        session_id, agent_id = None):
    c = HttpClient(job_server)
    d = dict(build_id = build_id, parent = parent_session,
             session_id = session_id, agent_id = agent_id)
    c.call('/session/created', input = json.dumps(d))


def dispatch(input):
    build_id = input['build_id']
    labels = input['labels']
    job_server = input['job_server']
    parent = input.get('parent_session')
    labels.remove("any")

    session_id = random_sha1()
    input['session_id'] = session_id

    db = conn()
    alloc_key = KEY_ALLOCATION % random_sha1()

    lkeys = [KEY_LABEL % label for label in labels]
    lkeys.append(KEY_AVAILABLE)

    while True:
        with db.pipeline() as pipe:
            try:
                pipe.watch(KEY_AVAILABLE)
                pipe.sinterstore(alloc_key, lkeys)
                agent_id = pipe.spop(alloc_key)
                if not agent_id:
                    dispatch_later(pipe, input)
                    pipe.delete(alloc_key)
                    pipe.execute()
                    report_to_jobserver(job_server, build_id, parent,
                                        session_id)
                else:
                    info = allocate(pipe, agent_id, session_id)
                    pipe.delete(alloc_key)
                    pipe.execute()

                    if not info:
                        continue
                    url = "http://%s:%s" % (info["ip"], info["port"])
                    do_dispatch(db, agent_id, url, input)
                    report_to_jobserver(job_server, build_id, parent,
                                        session_id, agent_id)
                return 'S' + session_id
            except redis.WatchError:
                continue


class DispatchBuild:
    def POST(self):
        input = json.loads(web.data())

        session_id = dispatch(input)
        return jsonify(id = session_id)


class GetDispatchedResult:
    def GET(self, session_id):
        db = conn()
        while True:
            info = db.get(KEY_DISPATCH_INFO % session_id)
            if not info:
                abort(404, "Dispatch ID not found")
            info = json.loads(info)
            if info['state'] == DISPATCH_STATE_DONE:
                return jsonify(result = info['result'])
            time.sleep(0.5)


class GetInfo:
    def GET(self):
        # Get queue
        db = conn()
        queue = []
        for did in db.zrange(KEY_QUEUE, 0, -1):
            info = db.get(KEY_DISPATCH_INFO % did)
            if info:
                info = json.loads(info)
                queue.append({"id": did,
                              "labels": info["labels"]})
        all = []
        for agent_id in db.smembers(KEY_ALL):
            info = db.get(KEY_AGENT % agent_id)
            if info:
                info = json.loads(info)
                all.append({"ip": info["ip"],
                            "port": info["port"],
                            "state": info["state"],
                            "seen": info["seen"],
                            "labels": info["labels"]})
        return jsonify(queue = queue,
                       agent_no = len(all),
                       agents = all)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    parser = OptionParser()
    parser.add_option("-p", "--port", dest = "port", default = 6699,
                      help = "port to use")
    parser.add_option("--test",
                      action = "store_true", dest = "test", default = False)
    (opts, args) = parser.parse_args()

    web.httpserver.runsimple(app.wsgifunc(), ("0.0.0.0", int(opts.port)))
