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


KEY_AVAILABLE = 'available'

KEY_LABEL = 'label:%s'
KEY_AGENT = 'agent:info:%s'     # -> {state:, job_no:, ts_allocated:}
KEY_TOKEN = 'token:%s'
KEY_ALLOCATION = "alloc:%s"
KEY_ALL = 'all'
ALLOCATION_EXPIRY_TTL = 1 * 60
SEEN_EXPIRY_TTL = 2 * 60

STATE_INACTIVE = "inactive"
STATE_AVAIL = "available"
STATE_PENDING = "pending"
STATE_BUSY = "busy"

urls = (
    '/register/([0-9a-f]+).json', 'Register',
    '/checkin/([0-9a-f]+)/([a-z]+)/([0-9]+).json', 'CheckIn',
    '/allocate/(.+).json',       'Allocate',
)

app = web.application(urls, globals())


pool = redis.ConnectionPool(host='localhost', port=6379, db=0)


def get_ts():
    return int(time.time())


def jsonify(**kwargs):
    web.header('Content-Type', 'application/json')
    return json.dumps(kwargs)


def abort(status, data):
    print("> %s" % data)
    raise web.webapi.HTTPError(status = status, data = data)


def conn():
    r = redis.Redis(connection_pool=pool)
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
                "job_no": old_info.get("job_no", 0),
                "ts_alloc": 0,
                "token_id": token_id,
                "seen": get_ts(),
                "labels": input["labels"]}

        db.set(KEY_AGENT % agent_id, json.dumps(info))
        db.sadd(KEY_ALL, agent_id)

        for label in input["labels"]:
            db.sadd(KEY_LABEL % label, agent_id)

        db.set(KEY_TOKEN % token_id, agent_id)
        return jsonify(token = token_id,
                       job_no = info["job_no"])


class CheckIn:
    def POST(self, token_id, status, job_no):
        job_no = int(job_no)
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
                    if info["state"] == STATE_INACTIVE and status == "available":
                        info["state"] = STATE_AVAIL
                        pipe.sadd(KEY_AVAILABLE, agent_id)
                    elif info["state"] == STATE_AVAIL and status == "available":
                        pass
                    elif info["state"] == STATE_PENDING and status == "busy" and \
                            info["job_no"] == job_no:
                        info["state"] = STATE_BUSY
                    elif info["state"] == STATE_PENDING and \
                            status == "available" and \
                            info["ts_alloc"] + ALLOCATION_EXPIRY_TTL < now:
                        print("%s expired allocation" % agent_id)
                        info["state"] = STATE_AVAIL
                        pipe.sadd(KEY_AVAILABLE, agent_id)
                    elif info["state"] == STATE_BUSY and status == "available" and \
                            info["job_no"] == job_no:
                        info["state"] = STATE_AVAIL
                        pipe.sadd(KEY_AVAILABLE, agent_id)
                    elif info["state"] == STATE_BUSY and status == "busy":
                        pass
                    else:
                        logging.error("info = %s, status = %s, job_no = %s" % \
                                          (info, status, job_no))
                    # We always update this - to refresh 'seen'
                    pipe.set(KEY_AGENT % agent_id, json.dumps(info))
                    pipe.execute()
                    break
            except redis.WatchError:
                continue

        return jsonify(status = "ok",
                       state = info["state"],
                       job_no = info["job_no"])


def allocate(pipe, agent_id):
    info = json.loads(pipe.get(KEY_AGENT % agent_id))
    pipe.multi()
    if info["state"] != "available":
        return None

    pipe.srem(KEY_AVAILABLE, agent_id)

    # verify the 'seen' so that it's not too old
    if info["seen"] + SEEN_EXPIRY_TTL < int(time.time()):
        print("Agent %s didn't check in - dropping" % agent_id)
        info["state"] = STATE_INACTIVE
        pipe.set(KEY_AGENT % agent_id, json.dumps(info))
        pipe.execute()
        return None

    job_no = info["job_no"] + 1
    info["job_no"] = job_no
    info["state"] = STATE_PENDING
    info["ts_alloc"] = get_ts()
    pipe.set(KEY_AGENT % agent_id, json.dumps(info))
    pipe.execute()
    return info


class Allocate:
    def POST(self, labels):
        labels = labels.split(",")
        labels.remove("any")

        db = conn()
        alloc_key = KEY_ALLOCATION % random_sha1()

        lkeys = [KEY_LABEL % label for label in labels]
        lkeys.append(KEY_AVAILABLE)
        with db.pipeline() as pipe:
            while True:
                try:
                    pipe.watch(KEY_AVAILABLE)
                    pipe.sinterstore(alloc_key, lkeys)
                    agent_id = pipe.spop(alloc_key)
                    if not agent_id:
                        pipe.delete(alloc_key)
                        return jsonify(status = "empty")

                    info = allocate(pipe, agent_id)
                    if info:
                        break
                except redis.WatchError:
                    continue

        db.delete(alloc_key)
        return jsonify(status = "ok", agent = agent_id,
                       ip = info["ip"], port = info["port"],
                       job_token = "%d" % info["job_no"],
                       url = "http://%s:%s" % (info["ip"], info["port"]))


if __name__ == "__main__":
    parser = OptionParser()
    parser.add_option("-p", "--port", dest = "port", default = 6699,
                      help = "port to use")
    parser.add_option("--test",
                      action = "store_true", dest = "test", default = False)
    (opts, args) = parser.parse_args()

    web.httpserver.runsimple(app.wsgifunc(), ("0.0.0.0", int(opts.port)))
