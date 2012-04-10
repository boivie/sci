import json
import sys
sys.path.append("../..")
from flask import Blueprint, render_template, url_for, request, redirect, abort
from sci.http_client import HttpClient, HttpError

app = Blueprint('builds', __name__, template_folder='templates')


def js():
    return HttpClient('http://127.0.0.1:6697')


@app.route('/<id>/edit', methods = ['GET'])
def edit(id):
    return "Edit"


@app.route('/<id>/start', methods = ['POST'])
def start(id):
    # Gather build parameters
    parameters = {}
    for name in request.form:
        if name.startswith("param_"):
            parameters[name[6:]] = request.form[name]
    data = {'parameters': parameters,
            'description': request.form.get('description', '')}
    info = js().call('/build/start/%s' % id, input = data)
    print(info)
    return "Build ID %s" % info['id']


@app.route('/<id>/start', methods = ['GET'])
def show_start(id):
    info = js().call('/job/%s' % id)
    params = info['parameters']
    for k, v in params.iteritems():
        # 'default' doesn't play well in jquery.tmpl - why?
        if 'default' in v:
            v['def'] = v['default']
            del v['default']

    params = params.values()
    params.sort(lambda a, b: cmp(a['name'], b['name']))

    return render_template('job_start.html',
                           id = id,
                           name = id,
                           active_tab = 'start',
                           params = params,
                           post_url = url_for('.start', id = id),
                           job = info)


@app.route('/<id>/home', methods = ['GET'])
@app.route('/<id>', methods = ['GET'])
def show_home(id):
    info = js().call('/job/%s' % id)
    info['settings']['recipe_url'] = url_for('recipes.show',
                                             id = info['settings']['recipe_name'])
    return render_template('job_settings.html',
                           id = id,
                           name = id,
                           active_tab = 'home',
                           job = info)


@app.route('/<id>/history', methods = ['GET'])
def show_history(id):
    info = js().call('/job/%s' % id)
    return render_template('job_history.html',
                           id = id,
                           job = info,
                           active_tab = 'history',
                           name = id)


def find_same_entry(log, session_no, t):
    for e in log:
        if e['s'] == session_no and e['type'] == t:
            return e
    return None


def find_other_entry(log, session_no, t):
    for e in log:
        if e['type'] == t and e['params']['session_no'] == session_no:
            return e
    return None


def simplify_log(log):
    result = []
    for i in range(len(log)):
        skip = False
        entry = log[i]
        if entry['type'] == 'step-begun':
            entry['end'] = find_same_entry(log[i:], entry['s'], 'step-done')
        elif entry['type'] == 'step-done':
            skip = True
        elif entry['type'] == 'run-async':
            entry['end'] = find_other_entry(log[i:], entry['params']['session_no'], 'async-joined')
        if not skip:
            result.append(entry)
    return result


@app.route('/<id>/latest', methods = ['GET'])
def show_latest(id):
    info = js().call('/job/%s' % id)
    return show_build(id, info.get('latest_no', 0), info, 'latest')


@app.route('/<id>/success', methods = ['GET'])
def show_success(id):
    info = js().call('/job/%s' % id)
    return show_build(id, info.get('success_no', 0), info, 'success')


@app.route('/<id>/<int:build_no>', methods = ['GET'])
def show_build(id, build_no, info = None, active_tab = None):
    if not info:
        info = js().call('/job/%s' % id)
    if build_no != 0:
        info = js().call('/build/%s,%d' % (id, build_no))
        build_info = info['build']
        build_info['job_url'] = url_for('.show_home', id = build_info['job_name'])
        build_info['recipe_url'] = url_for('recipes.show', id = build_info['recipe_name'])
    else:
        build_info = {}

    log = [json.loads(l) for l in info.get('log', [])]
    for l in log:
        l['dt'] = (l['t'] - log[0]['t']) / 1000
    log = simplify_log(log)
    return render_template('job_show.html',
                           id = id,
                           name = id,
                           build_no = build_no,
                           active_tab = active_tab,
                           job = info,
                           build = build_info,
                           log = log)


@app.route('/', methods = ['GET'])
def index():
    jobs = js().call('/job')['jobs']

    return render_template('jobs_list.html',
                           jobs = jobs)
