import json
import logging
import time

import redis
import web

from sci.utils import random_sha1
from sci.http_client import HttpClient
from jobserver.utils import get_ts
from jobserver.db import conn
from jobserver.webutils import abort, jsonify

urls = (
    '/available/A([0-9a-f]{40})', 'CheckInAvailable',
    '/busy/A([0-9a-f]{40})',      'CheckInBusy',
    '/dispatch',                  'DispatchBuild',
    '/agents',                    'GetAgentsInfo',
    '/queue',                     'GetQueueInfo',
    '/ping/A([0-9a-f]{40})',      'Ping',
    '/register',                  'Register',
    '/result/S([0-9a-f]{40})',    'GetDispatchedResult',
)

agent_app = web.application(urls, locals())


KEY_LABEL = 'ahq:label:%s'
KEY_AGENT = 'agent:info:%s'
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


class Register:
    def POST(self):
        input = json.loads(web.data())
        db = conn()
        agent_id = input['id']

        info = {"ip": web.ctx.ip,
                'nick': input.get('nick', ''),
                "port": input["port"],
                "state": STATE_INACTIVE,
                "seen": get_ts(),
                "labels": ",".join(input["labels"])}

        db.hmset(KEY_AGENT % agent_id, info)
        db.sadd(KEY_ALL, agent_id)

        for label in input["labels"]:
            db.sadd(KEY_LABEL % label, agent_id)

        return jsonify()


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


def handle_last_results(db, data):
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
    def POST(self, agent_id):
        agent_id = 'A' + agent_id
        db = conn()

        # Do we have results from a previous dispatch?
        handle_last_results(db, web.data())

        db.hset(KEY_AGENT % agent_id, 'state', STATE_AVAIL)
        db.hset(KEY_AGENT % agent_id, 'seen', get_ts())
        # TODO: Race condition -> we may be inside allocate() right now
        db.sadd(KEY_AVAILABLE, agent_id)
        return jsonify()


class CheckInBusy:
    def POST(self, agent_id):
        agent_id = 'A' + agent_id
        db = conn()

        db.hsetnx(KEY_AGENT % agent_id, 'state', STATE_BUSY)
        db.hsetnx(KEY_AGENT % agent_id, 'seen', get_ts())
        return jsonify()


class Ping:
    def POST(self, agent_id):
        agent_id = 'A' + agent_id
        db = conn()

        db.hsetnx(KEY_AGENT % agent_id, 'seen', get_ts())
        return jsonify()


def allocate(pipe, agent_id, session_id):
    """Starts multi, doesn't exec"""
    pipe.watch(KEY_AGENT % agent_id)
    info = pipe.hgetall(KEY_AGENT % agent_id)
    info['seen'] = int(info['seen'])

    pipe.multi()
    pipe.srem(KEY_AVAILABLE, agent_id)
    if info['state'] != STATE_AVAIL:
        return None

    # verify the 'seen' so that it's not too old
    if info['seen'] + SEEN_EXPIRY_TTL < int(time.time()):
        print("%s didn't check in - dropping" % agent_id)
        pipe.hset(KEY_AGENT % agent_id, 'state', STATE_INACTIVE)
        return None

    pipe.hset(KEY_AGENT % agent_id, 'state', STATE_PENDING)
    pipe.hset(KEY_AGENT % agent_id, 'dispatch_id', session_id)
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


def dispatch(input):
    labels = input['labels']
    labels.remove("any")

    if input.get('session_id'):
        session_id = input['session_id']
    else:
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
                    logging.debug("No agent available - queuing")
                    dispatch_later(pipe, input)
                    pipe.delete(alloc_key)
                    pipe.execute()
                else:
                    logging.debug("Dispatching to %s" % agent_id)
                    info = allocate(pipe, agent_id, session_id)
                    pipe.delete(alloc_key)
                    pipe.execute()

                    if not info:
                        continue
                    url = "http://%s:%s" % (info["ip"], info["port"])
                    do_dispatch(db, agent_id, url, input)

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


class GetAgentsInfo:
    def GET(self):
        db = conn()
        all = []
        for agent_id in db.smembers(KEY_ALL):
            info = db.hgetall(KEY_AGENT % agent_id)
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
        db = conn()
        queue = []
        for did in db.zrange(KEY_QUEUE, 0, -1):
            info = db.get(KEY_DISPATCH_INFO % did)
            if info:
                info = json.loads(info)
                queue.append({"id": did,
                              "labels": info["labels"]})
        return jsonify(queue = queue)
