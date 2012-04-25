import os

JS_PATH = os.path.dirname(__file__)
SS_PATH = os.path.dirname(__file__)

JS_SERVER_NAME = 'localhost:6697'
SS_SERVER_NAME = 'localhost:6698'
SS_URL = 'http://' + SS_SERVER_NAME

if os.environ['_sci_kind'] == 'ss':
    SERVER_NAME = SS_SERVER_NAME
elif os.environ['_sci_kind'] == 'js':
    SERVER_NAME = JS_SERVER_NAME
else:
    raise RuntimeError("_sci_kind not set")
