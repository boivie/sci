#!/usr/bin/env python
"""
    sci.jobserver
    ~~~~~~~~~~~~~

    Job Server

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
import logging, os

from flask import Flask, jsonify

from jobserver.build_app import app as build_app
from jobserver.slog_app import app as slog_app
from jobserver.job_app import app as job_app
from jobserver.recipe_app import app as recipe_app
from jobserver.agent_app import app as agent_app

os.environ['_sci_kind'] = 'js'
app = Flask(__name__)
app.register_blueprint(build_app, url_prefix='/build')
app.register_blueprint(slog_app, url_prefix='/slog')
app.register_blueprint(job_app, url_prefix='/job')
app.register_blueprint(recipe_app, url_prefix='/recipe')
app.register_blueprint(agent_app, url_prefix='/agent')
app.config.from_envvar('SCI_SETTINGS')

if app.debug:
    logging.basicConfig(level=logging.DEBUG)


@app.route("/info", methods = ['GET'])
def getinfo():
    return jsonify(ss_url = app.config['SS_URL'])

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=6697, debug = True, threaded = True)
