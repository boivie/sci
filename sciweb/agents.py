import sys
sys.path.append("../..")
from flask import Blueprint, render_template
from sci.http_client import HttpClient

app = Blueprint('agents', __name__, template_folder='templates')


def ahq():
    return HttpClient('http://localhost:6697')


@app.route('/edit/<id>', methods = ['GET'])
def edit(id):
    return "Edit"


@app.route('/show/<id>', methods = ['GET'])
def show(id):
    return "Show"


@app.route('/', methods = ['GET'])
def index():
    agents = ahq().call('/agent/agents')['agents']
    for agent in agents:
        if not agent['nick']:
            del agent['nick']

    return render_template('agents_list.html',
                           agents = agents)
