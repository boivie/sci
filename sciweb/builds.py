import json
import sys
sys.path.append("../..")
from flask import Blueprint, render_template, url_for, request, redirect, abort
from sci.http_client import HttpClient, HttpError

app = Blueprint('builds', __name__, template_folder='templates')


def js():
    return HttpClient('http://127.0.0.1:6697')


@app.route('/edit/<id>', methods = ['GET'])
def edit(id):
    return "Edit"


@app.route('/start/<id>', methods = ['POST'])
def start(id):
    # Gather build parameters
    parameters = {}
    for name in request.form:
        if name.startswith("param_"):
            parameters[name[6:]] = request.form[name]
    data = {'parameters': parameters}
    info = js().call('/build/start/%s' % id, input = data)
    print(info)
    return "Build ID %s" % info['id']


def show_start(info, id):
    rref = info['settings']['recipe_name']
    if info['settings']['recipe_ref']:
        rref = info['settings']['recipe_ref']
    recipe = js().call('/recipe/%s.json' % rref)
    params = []
    for k, v in recipe['metadata']['Parameters'].iteritems():
        v['name'] = k
        v['required'] = v.get('required', False)
        v['read-only'] = v.get('read-only', False)
        v['def'] = v.get('default', '')
        params.append(v)

    params.sort(lambda a, b: cmp(a['name'], b['name']))

    return render_template('job_start.html',
                           job_url = url_for('.show_job', id = id),
                           name = id,
                           active_tab = 'start',
                           params = params,
                           post_url = url_for('.start', id = id),
                           job = info)


def show_settings(info, id):
    info['settings']['recipe_url'] = url_for('recipes.show',
                                             id = info['settings']['recipe_name'])
    return render_template('job_settings.html',
                           job_url = url_for('.show_job', id = id),
                           name = id,
                           active_tab = 'settings',
                           job = info)


def show_history(info, id):
    return render_template('job_history.html',
                           job_url = url_for('.show_job', id = id),
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


def show_build(info, id, build_no, active_tab):
    if build_no != 0:
        info = js().call('/build/%s,%d' % (id, build_no))
        build_info = info['build']
        build_info['job_url'] = url_for('.show_job', id = build_info['job_name'])
        build_info['recipe_url'] = url_for('recipes.show', id = build_info['recipe_name'])
    else:
        build_info = {}

    log = [json.loads(l) for l in info.get('log', [])]
    for l in log:
        l['dt'] = (l['t'] - log[0]['t']) / 1000
    log = simplify_log(log)
    return render_template('job_show.html',
                           job_url = url_for('.show_job', id = id),
                           name = id,
                           build_no = build_no,
                           active_tab = active_tab,
                           job = info,
                           build = build_info,
                           log = log)


@app.route('/show/<id>', methods = ['GET'])
def show_job(id):
    args = id.split(',')
    id = args[0]
    show = args[1] if len(args) > 1 else 'latest'

    info = js().call('/job/%s,queue,history' % id)
    if show == 'start':
        return show_start(info, id)
    elif show == 'settings':
        return show_settings(info, id)
    if show == 'latest':
        return show_build(info, id, info.get('latest_no', 0), 'latest')
    elif show == 'success':
        return show_build(info, id, info.get('success_no', 0), 'success')
    elif show == 'history':
        return show_history(info, id)
    else:
        try:
            build_no = int(show)
        except ValueError:
            abort(404)
        else:
            return show_build(info, id, build_no, 'history')


@app.route('/', methods = ['GET'])
def index():
    jobs = js().call('/job')['jobs']
    for job in jobs:
        job['url'] = url_for('.show_job', id = job['id'])

    return render_template('jobs_list.html',
                           jobs = jobs)
