from flask import Blueprint, render_template, current_app
from sci.http_client import HttpClient

app = Blueprint('agents', __name__, template_folder='templates')


def ahq():
    return HttpClient('http://' + current_app.config['JS_SERVER_NAME'])


@app.route('/edit/<id>', methods = ['GET'])
def edit(id):
    return "Edit"


@app.route('/show/<id>', methods = ['GET'])
def show(id):
    info = ahq().call('/agent/details/%s' % id)
    print(info)
    return render_template('agent_show.html',
                           agent = info)


@app.route('/', methods = ['GET'])
def index():
    agents = ahq().call('/agent/list')['agents']
    for agent in agents:
        if not agent['nick']:
            del agent['nick']

    active_agents = [a for a in agents if a['state'] != 'inactive']
    idle_agents = [a for a in agents if a['state'] == 'inactive']

    return render_template('agents_list.html',
                           agents = active_agents,
                           idle_agents = idle_agents)
