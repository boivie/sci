#!/usr/bin/env python
import logging
import os

from ss.app import app


os.environ['_sci_kind'] = 'ss'
app.config.from_envvar('SCI_SETTINGS')

if app.debug:
    logging.basicConfig(level=logging.DEBUG)


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=6698, debug = True, threaded = True)
