import os

JS_PATH = os.path.dirname(__file__)
SS_PATH = os.path.dirname(__file__)

JS_SERVER_NAME = 'localhost:6697'
SS_SERVER_NAME = 'localhost:6698'
SW_SERVER_NAME = 'localhost:5000'
SS_URL = 'http://' + SS_SERVER_NAME
DEBUG = True

if os.environ['_sci_kind'] == 'ss':
    SERVER_NAME = SS_SERVER_NAME
elif os.environ['_sci_kind'] == 'js':
    SERVER_NAME = JS_SERVER_NAME
elif os.environ['_sci_kind'] == 'sw':
    SERVER_NAME = SW_SERVER_NAME
else:
    raise RuntimeError("_sci_kind not set")
