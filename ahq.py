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
KEY_TICKET_INFO = 'ticket:info:%s'
KEY_TICKET_SLAVES = 'ticket:q:%s'
KEY_QUEUE = 'ticket_queue'
KEY_ALL = 'all'
ALLOCATION_EXPIRY_TTL = 1 * 60
SEEN_EXPIRY_TTL = 2 * 60
KEY_TICKET_TTL = 1 * 60

STATE_INACTIVE = "inactive"
STATE_AVAIL = "available"
STATE_PENDING = "pending"
STATE_BUSY = "busy"

urls = (
    '/register/([0-9a-f]+).json', 'Register',
    '/checkin/([0-9a-f]+)/([a-z]+)/([0-9]+).json', 'CheckIn',
    '/allocate.json',         'AllocateLabels',
    '/tickets.json',          'AllocateTickets',
    '/info.json',             'GetInfo'
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


def make_avail_or_give_to_queue(pipe, agent_id, agent_info):
    """Starts multi, doesn't exec"""
    pipe.watch(KEY_QUEUE)
    queue = pipe.zrange(KEY_QUEUE, 0, -1)
    expired_tickets = []
    for ticket_id in queue:
        ticket_info = pipe.get(KEY_TICKET_INFO % ticket_id)
        if not ticket_info:
            # Expired. Delete it.
            expired_tickets.append(ticket_id)
            continue
        ticket_info = json.loads(ticket_info)
        # Do we fulfill its requirements?
        if set(ticket_info["labels"]).issubset(set(agent_info["labels"])):
            # Yup. Put it as 'pending' in the ticket's queue
            job_no = agent_info["job_no"] + 1
            agent_info["job_no"] = job_no
            agent_info["state"] = STATE_PENDING
            agent_info["ts_alloc"] = get_ts()
            pipe.multi()
            expired_tickets.append(ticket_id)
            for t in expired_tickets:
                pipe.zrem(KEY_QUEUE, t)
            pipe.rpush(KEY_TICKET_SLAVES % ticket_id, agent_id)
            return ticket_id

    # Nope. No tickets -> put it as available.
    pipe.multi()
    if expired_tickets:
        pipe.zrem(KEY_QUEUE, expired_tickets)
    agent_info["state"] = STATE_AVAIL
    pipe.sadd(KEY_AVAILABLE, agent_id)
    return None


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
                    ticket = None
                    pipe.watch(KEY_AGENT % agent_id)
                    info = json.loads(pipe.get(KEY_AGENT % agent_id))

                    info["seen"] = now
                    if info["state"] == STATE_INACTIVE and status == "available":
                        ticket = make_avail_or_give_to_queue(pipe, agent_id, info)
                    elif info["state"] == STATE_AVAIL and status == "available":
                        pipe.multi()
                        pass
                    elif info["state"] == STATE_PENDING and status == "busy" and \
                            info["job_no"] == job_no:
                        pipe.multi()
                        info["state"] = STATE_BUSY
                    elif info["state"] == STATE_PENDING and \
                            status == "available" and \
                            info["ts_alloc"] + ALLOCATION_EXPIRY_TTL < now:
                        logging.info("A%s expired allocation" % agent_id)
                        ticket = make_avail_or_give_to_queue(pipe, agent_id, info)
                    elif info["state"] == STATE_BUSY and status == "available" and \
                            info["job_no"] == job_no:
                        ticket = make_avail_or_give_to_queue(pipe, agent_id, info)
                    elif info["state"] == STATE_BUSY and status == "busy":
                        pipe.multi()
                        pass
                    else:
                        pipe.multi()
                        logging.error("info = %s, status = %s, job_no = %s" % \
                                          (info, status, job_no))
                    # We always update this - to refresh 'seen'
                    pipe.set(KEY_AGENT % agent_id, json.dumps(info))
                    pipe.execute()
                    # We succeeded!
                    if ticket:
                        logging.debug("A%s checked in -> T%s" % (agent_id, ticket))
                    else:
                        logging.debug("A%s checked in" % agent_id)
                    break
            except redis.WatchError:
                continue

        return jsonify(status = "ok",
                       state = info["state"],
                       job_no = info["job_no"])


def allocate(pipe, agent_id):
    """Starts multi, doesn't exec"""
    info = json.loads(pipe.get(KEY_AGENT % agent_id))
    pipe.multi()
    if info["state"] != "available":
        return None

    pipe.srem(KEY_AVAILABLE, agent_id)

    # verify the 'seen' so that it's not too old
    if info["seen"] + SEEN_EXPIRY_TTL < int(time.time()):
        print("A%s didn't check in - dropping" % agent_id)
        info["state"] = STATE_INACTIVE
        pipe.set(KEY_AGENT % agent_id, json.dumps(info))
        return None

    job_no = info["job_no"] + 1
    info["job_no"] = job_no
    info["state"] = STATE_PENDING
    info["ts_alloc"] = get_ts()
    pipe.set(KEY_AGENT % agent_id, json.dumps(info))
    return info


def get_ticket(pipe, labels):
    """Starts multi, doesn't exec"""
    ticket_id = random_sha1()

    pipe.multi()
    pipe.setex(KEY_TICKET_INFO % ticket_id, KEY_TICKET_TTL,
               json.dumps({"labels": labels}))
    ts = float(time.time() * 1000)
    pipe.zadd(KEY_QUEUE, ts, ticket_id)
    return ticket_id


def format_result(agent_id, info):
    url = "http://%s:%s" % (info["ip"], info["port"])
    return dict(status = "ok", agent = agent_id,
                ip = info["ip"], port = info["port"],
                job_token = "%d" % info["job_no"],
                url = url)


class AllocateLabels:
    def POST(self):
        input = json.loads(web.data())
        labels = input["labels"]
        labels.remove("any")

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
                        ticket_id = get_ticket(pipe, labels)
                        pipe.delete(alloc_key)
                        pipe.execute()
                        logging.debug("Handed out T%s" % ticket_id)
                        return jsonify(status = "queued", ticket = ticket_id)

                    info = allocate(pipe, agent_id)
                    if not info:
                        continue
                    pipe.delete(alloc_key)
                    pipe.execute()
                    logging.debug("Allocated A%s" % agent_id)
                    return json.dumps(format_result(agent_id, info))
                except redis.WatchError:
                    continue


class AllocateTickets:
    def POST(self):
        input = json.loads(web.data())
        tickets = input["tickets"]
        ticket_keys = [KEY_TICKET_SLAVES % t for t in tickets]
        db = conn()
        count = 0
        while True:
            for t in tickets:
                db.expire(KEY_TICKET_INFO % t, KEY_TICKET_TTL)
            result = db.blpop(ticket_keys, 1)
            if not result:
                count += 1
                if count == 10:
                    yield json.dumps({"status": "failed"})
                    break
                yield "\n"
                continue
            ticket_key, agent_id = result
            ticket_id = ticket_key[-40:]
            # It is aready prepared for us. Return it.
            info = json.loads(db.get(KEY_AGENT % agent_id))
            res = format_result(agent_id, info)
            res["ticket"] = ticket_id
            tickets.remove(ticket_id)
            logging.debug("Traded A%s from T%s" % (agent_id, ticket_id))
            yield json.dumps(res)
            break


class GetInfo:
    def GET(self):
        # Get queue
        db = conn()
        queue = []
        for ticket_id in db.zrange(KEY_QUEUE, 0, -1):
            info = db.get(KEY_TICKET_INFO % ticket_id)
            if info:
                info = json.loads(info)
                queue.append({"ticket": ticket_id,
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
