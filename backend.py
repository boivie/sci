#!/usr/bin/env python
import logging
from pyres.worker import Worker

logging.basicConfig(level=logging.INFO)

Worker.run(['queue'], 'localhost:6379', None)
