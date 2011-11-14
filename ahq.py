#!/usr/bin/env python
"""
    sci.ahq
    ~~~~~~~

    Agent Coordinator

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
from optparse import OptionParser
import web, redis, json, time


KEY_AVAILABLE = 'available.%s'
KEY_ALL = 'all'
KEY_AGENT = 'agent:%s'
EXPIRY_TTL = 2 * 60

urls = (
    '/checkin/([0-9a-f]+).json', 'CheckIn',
    '/allocate/(.+).json',       'Allocate',
)

app = web.application(urls, globals())


def jsonify(**kwargs):
    web.header('Content-Type', 'application/json')
    return json.dumps(kwargs)


def conn():
    return redis.StrictRedis()


class CheckIn:
    def POST(self, agent_id):
        # TODO: Add a key to authenticate the agent
        info = json.loads(web.data())
        db = conn()
        db.set(KEY_AGENT % agent_id, json.dumps({"ip": web.ctx.ip,
                                                 "port": info["port"],
                                                 "status": info["status"],
                                                 "seen": int(time.time())}))
        label = "any"
        db.sadd(KEY_ALL, agent_id)
        if info["status"] == "available":
            db.sadd(KEY_AVAILABLE % label, agent_id)
        else:
            db.srem(KEY_AVAILABLE % label, agent_id)
        return jsonify(status = "ok")


class Allocate:
    def POST(self, label):
        label = "any"  # we don't support anything else yet
        db = conn()
        while True:
            agent_id = db.spop(KEY_AVAILABLE % label)
            if agent_id is None:
                return jsonify(status = "empty")
            # verify the 'seen' so that it's not too old
            info = db.get(KEY_AGENT % agent_id)
            if info is None:
                # Shouldn't happen. Try the next one
                print("FAILED TO FIND INFO ABOUT %s" % agent_id)
                continue
            info = json.loads(info)
            if info["status"] != "available":
                # A race condition - the agent just went offline
                print("Agent %s recently switched (%s)" % (agent_id, info["status"]))
                continue
            if info["seen"] + EXPIRY_TTL < int(time.time()):
                print("Agent %s didn't check in - dropping" % agent_id)
                continue
            info["status"] = "allocated"
            db.set(KEY_AGENT % agent_id, json.dumps(info))
            return jsonify(status = "ok", agent = agent_id,
                           ip = info["ip"], port = info["port"])


if __name__ == "__main__":
    parser = OptionParser()
    parser.add_option("-p", "--port", dest = "port", default = 6699,
                      help = "port to use")
    parser.add_option("--test",
                      action = "store_true", dest = "test", default = False)
    (opts, args) = parser.parse_args()

    web.httpserver.runsimple(app.wsgifunc(), ("0.0.0.0", int(opts.port)))
