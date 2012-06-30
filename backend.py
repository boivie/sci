#!/usr/bin/env python
import logging, time

from pyres.worker import Worker
import redis

logging.basicConfig(level=logging.INFO)

while True:
    try:
        Worker.run(['queue'], 'localhost:6379', None)
    except redis.exceptions.ConnectionError:
        print("Connection to redis lost - reconnecting in 2")
        time.sleep(2)
