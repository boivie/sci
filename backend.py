#!/usr/bin/env python
import json, logging, sys, time

import redis

from jobserver.queue import StartBuildQ, DispatchSession, AgentAvailable
from sci.http_client import HttpClient
from sci.utils import random_sha1
from jobserver.build import get_session
from jobserver.build import set_session_to_agent, set_session_queued
import jobserver.db as jdb


def dispatch_later(pipe, input):
    """Starts multi, doesn't exec"""
    session_id = input['session_id']
    pipe.multi()
    ts = float(time.time() * 1000)
    set_session_queued(pipe, session_id)
    pipe.zadd(jdb.KEY_QUEUE, ts, session_id)
    return session_id


def do_dispatch(db, agent_id, agent_url, input):
    print("DISPATCH TO AGENT, URL: '%s'" % agent_url)
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

    pipe.hset(jdb.KEY_AGENT % agent_id, 'state', jdb.AGENT_STATE_PENDING)
    pipe.hset(jdb.KEY_AGENT % agent_id, 'session', session_id)
    return info


def dispatch_be(session_id):
    db = jdb.conn()
    session = get_session(db, session_id)
    input = session['input']

    labels = input['labels']
    labels.remove("any")
    lkeys = [jdb.KEY_LABEL % label for label in labels]
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
                    set_session_to_agent(db, session_id, agent_id)
                    input['session_id'] = session_id
                    do_dispatch(db, agent_id, url, input)
                return
            except redis.WatchError:
                continue


def handle_agent_available(agent_id):
    db = jdb.conn()
    # TODO: Before adding it here, match it to the queue
    db.sadd(jdb.KEY_AVAILABLE, agent_id)


def worker(msg):
    item = json.loads(msg)
    logging.debug("Got msg '%s'" % item['type'])
    if item['type'] == StartBuildQ.type:
        client = HttpClient("http://localhost:6697")
        data = dict(build_id = item['params']['build_id'],
                    session_id = item['params']['session_id'][1:],
                    job_server = 'http://localhost:6697',
                    funname = None,
                    env = None,
                    args = [],
                    labels = ['any'],
                    kwargs = {})
        client.call('/agent/dispatch', input = json.dumps(data))

    elif item['type'] == DispatchSession.type:
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
