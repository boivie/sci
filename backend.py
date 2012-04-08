#!/usr/bin/env python
import json, logging, sys, time

import redis

from jobserver.queue import DispatchSession, AgentAvailable
from sci.http_client import HttpClient
from sci.utils import random_sha1
from jobserver.build import get_session, get_session_labels
from jobserver.build import set_session_to_agent, set_session_queued
import jobserver.db as jdb

JOBSERVER_URL = "http://localhost:6697"


def dispatch_later(pipe, session_id):
    """Starts multi, doesn't exec"""
    pipe.multi()
    ts = float(time.time() * 1000)
    set_session_queued(pipe, session_id)
    pipe.zadd(jdb.KEY_QUEUED_SESSIONS, ts, session_id)
    return session_id


def do_dispatch(db, agent_id, agent_info, session_id, session):
    agent_url = "http://%s:%s" % (agent_info["ip"], agent_info["port"])
    print("DISPATCH TO AGENT, URL: '%s'" % agent_url)

    set_session_to_agent(db, session_id, agent_id)
    input = dict(session_id = session_id,
                 build_id = session_id.split('-')[0],
                 job_server = JOBSERVER_URL,
                 run_info = session['run_info'])
    client = HttpClient(agent_url)
    client.call('/dispatch', input = json.dumps(input))


def allocate(pipe, agent_id, session_id):
    """Starts multi, doesn't exec"""
    # The agent may become inactive
    pipe.watch(jdb.KEY_AGENT % agent_id)
    info = pipe.hgetall(jdb.KEY_AGENT % agent_id)
    info['seen'] = int(info['seen'])

    pipe.multi()
    pipe.srem(jdb.KEY_AVAILABLE, agent_id)
    if info['state'] != jdb.AGENT_STATE_AVAIL:
        return None

    # verify the 'seen' so that it's not too old
    #if info['seen'] + SEEN_EXPIRY_TTL < int(time.time()):
    #    print("%s didn't check in - dropping" % agent_id)
    #    pipe.hset(jdb.KEY_AGENT % agent_id, 'state', STATE_INACTIVE)
    #    return None

    pipe.hmset(jdb.KEY_AGENT % agent_id, {'state': jdb.AGENT_STATE_PENDING,
                                          'session': session_id})
    return info


def dispatch_be(session_id):
    db = jdb.conn()
    session = get_session(db, session_id)
    lkeys = [jdb.KEY_LABEL % label for label in session['labels']]
    lkeys.append(jdb.KEY_AVAILABLE)

    alloc_key = jdb.KEY_ALLOCATION % random_sha1()

    while True:
        with db.pipeline() as pipe:
            try:
                pipe.watch(jdb.KEY_AVAILABLE)
                pipe.sinterstore(alloc_key, lkeys)
                agent_id = pipe.spop(alloc_key)
                if not agent_id:
                    logging.debug("No agent available - queuing")
                    dispatch_later(pipe, session_id)
                    pipe.delete(alloc_key)
                    pipe.execute()
                else:
                    logging.debug("Dispatching to %s" % agent_id)
                    agent_info = allocate(pipe, agent_id, session_id)
                    pipe.delete(alloc_key)
                    pipe.execute()

                    if not agent_info:
                        continue

                    do_dispatch(db, agent_id, agent_info, session_id, session)
                return
            except redis.WatchError:
                continue


def handle_agent_available(agent_id):
    db = jdb.conn()
    matched = None
    agent_labels = set(db.hget(jdb.KEY_AGENT % agent_id, 'labels').split(','))
    queued = db.zrange(jdb.KEY_QUEUED_SESSIONS, 0, -1)
    if queued:
        logging.info("Agent %s available - matching against "
                     "%d queued sessions" % (agent_id, len(queued)))
        for session_id in queued:
            labels = get_session_labels(db, session_id)
            if labels.issubset(agent_labels):
                matched = session_id
                break
        db.zrem(jdb.KEY_QUEUED_SESSIONS, matched)
        logging.debug("Matched against %s" % matched)
    else:
        logging.info("Agent %s available - nothing queued." % agent_id)

    if matched:
        session = get_session(db, matched)
        agent_info = db.hgetall(jdb.KEY_AGENT % agent_id)
        do_dispatch(db, agent_id, agent_info, matched, session)
    else:
        db.sadd(jdb.KEY_AVAILABLE, agent_id)


def worker(msg):
    item = json.loads(msg)
    logging.debug("Got msg '%s'" % item['type'])

    if item['type'] == DispatchSession.type:
        dispatch_be(item['params']['session_id'])

    elif item['type'] == AgentAvailable.type:
        handle_agent_available(item['params']['agent_id'])


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    logging.info("Backend ready to serve the world. And more.")
    db = jdb.conn()
    try:
        while True:
            q, item = db.blpop(jdb.KEY_QUEUE)
            worker(item)
    except KeyboardInterrupt:
        sys.exit(1)
