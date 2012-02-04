import sys
sys.path.append("../..")
from flask import Blueprint, render_template, url_for, request, redirect, abort
from sci.http_client import HttpClient, HttpError

app = Blueprint('agents', __name__, template_folder='templates')


def ahq():
    return HttpClient('http://127.0.0.1:6699')


@app.route('/edit/<id>', methods = ['GET'])
def edit(id):
    return "Edit"


@app.route('/show/<id>', methods = ['GET'])
def show(id):
    return "Show"


@app.route('/', methods = ['GET'])
def index():
    agents = ahq().call('/agents')['agents']
    for agent in agents:
        agent['url'] = url_for('.show', id = agent['id'])
        if not agent['nick']:
            del agent['nick']

    return render_template('agents_list.html',
                           agents = agents)
