import os

DEBUG = True

SECRET_KEY = 'testkey'

JS_PATH = os.path.dirname(__file__)
SS_PATH = os.path.dirname(__file__)

JS_SERVER_NAME = 'localhost:6697'
JS_SERVER_PORT = 6697
SS_SERVER_NAME = 'localhost:6698'
SS_SERVER_PORT = 6698
SW_SERVER_NAME = 'localhost:5000'
SW_SERVER_PORT = 5000
SS_URL = 'http://' + SS_SERVER_NAME

del os
