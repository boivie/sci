#!/usr/bin/env python
"""
    sci.web
    ~~~~~~~

    Frontend Web Server

    :copyright: (c) 2012 by Victor Boivie
    :license: Apache License 2.0
"""
import logging

from sciweb.app import app

app.config.from_object('sci_config')
app.config.from_envvar('SCI_SETTINGS', silent=True)
app.config['SERVER_NAME'] = app.config['SW_SERVER_NAME']

if app.debug:
    logging.basicConfig(level=logging.DEBUG)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=app.config['SW_SERVER_PORT'],
            debug = True, threaded = True)
