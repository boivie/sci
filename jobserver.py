#!/usr/bin/env python
"""
    sci.jobserver
    ~~~~~~~~~~~~~

    Job Server

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
import logging, os

from jobserver.app import app


os.environ['_sci_kind'] = 'js'
app.config.from_envvar('SCI_SETTINGS')

if app.debug:
    logging.basicConfig(level=logging.DEBUG)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=6697, debug = True, threaded = True)
