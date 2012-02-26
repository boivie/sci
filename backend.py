#!/usr/bin/env python
import json, logging, sys

import redis

from jobserver.queue import StartBuildQ, DispatchSession
from sci.http_client import HttpClient

from jobserver.agent_app import dispatch_be

redis_pool = redis.ConnectionPool(host='localhost', port=6379, db=0)
KEY_QUEUE = 'js:queue'


def conn():
    r = redis.StrictRedis(connection_pool=redis_pool)
    return r


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


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    db = conn()
    try:
        while True:
            q, item = db.blpop(KEY_QUEUE)
            worker(item)
    except KeyboardInterrupt:
        sys.exit(1)
