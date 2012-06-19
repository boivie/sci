#!/usr/bin/env python
import logging
import os

from sciweb.app import app


os.environ['_sci_kind'] = 'sw'
app.config.from_envvar('SCI_SETTINGS')

if app.debug:
    logging.basicConfig(level=logging.DEBUG)


if __name__ == "__main__":
    app.run(host='0.0.0.0', debug = True, threaded = True)
