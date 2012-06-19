from flask import Flask, jsonify

from jobserver.build_app import app as build_app
from jobserver.slog_app import app as slog_app
from jobserver.job_app import app as job_app
from jobserver.recipe_app import app as recipe_app
from jobserver.agent_app import app as agent_app

app = Flask(__name__)
app.register_blueprint(build_app, url_prefix='/build')
app.register_blueprint(slog_app, url_prefix='/slog')
app.register_blueprint(job_app, url_prefix='/job')
app.register_blueprint(recipe_app, url_prefix='/recipe')
app.register_blueprint(agent_app, url_prefix='/agent')


@app.route("/info", methods = ['GET'])
def getinfo():
    return jsonify(ss_url = app.config['SS_URL'])
