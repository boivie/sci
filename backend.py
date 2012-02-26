#!/usr/bin/env python
import json, logging, sys

import redis

from sci.queue import StartBuildQ
from sci.http_client import HttpClient

redis_pool = redis.ConnectionPool(host='localhost', port=6379, db=0)
KEY_QUEUE = 'js:queue'


def conn():
    r = redis.StrictRedis(connection_pool=redis_pool)
    return r


def worker(msg):
    item = json.loads(msg)
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


if __name__ == '__main__':
    db = conn()
    try:
        while True:
            logging.debug("Fetching a message")
            q, item = db.blpop(KEY_QUEUE)
            logging.debug("Got a msg")
            worker(item)
    except KeyboardInterrupt:
        sys.exit(1)
