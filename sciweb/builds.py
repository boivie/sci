import sys
sys.path.append("../..")
from flask import Blueprint, render_template, url_for, request, redirect, abort
from sci.http_client import HttpClient, HttpError

app = Blueprint('builds', __name__, template_folder='templates')


def js():
    return HttpClient('http://127.0.0.1:6697')


@app.route('/<id>/edit', methods = ['POST'])
def edit(id):
    try:
        js().call('/job/%s' % id,
                  input = dict(contents = request.form['contents'],
                               old = request.form['ref']))
    except HttpError as e:
        if e.code != 412:
            abort(500)
        else:
            pass
            # TODO
    return redirect(url_for('.show_home', id = id))


@app.route('/<id>/raw_edit', methods = ['GET'])
def show_raw_edit(id):
    info = js().call('/job/%s' % id, show = 'raw')
    return render_template('job_edit_raw.html',
                           id = id,
                           name = id,
                           active_tab = 'raw_edit',
                           job = info)


@app.route('/<id>/edit', methods = ['GET'])
def show_edit(id):
    recipes = js().call('/recipe')['recipes']

    info = js().call('/job/%s' % id)
    params = info['parameters']
    print(info)
    for k, v in params.iteritems():
        # 'default' doesn't play well in jquery.tmpl - why?
        if 'default' in v:
            v['def'] = v['default']
            del v['default']

    params = params.values()
    params.sort(lambda a, b: cmp(a['name'], b['name']))

    return render_template('job_edit.html',
                           id = id,
                           name = id,
                           active_tab = 'edit',
                           params = params,
                           post_url = url_for('.edit', id = id),
                           job = info,
                           recipes = recipes)


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
    return redirect(url_for('.show_build', id = id, build_no = info['number']))


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
                                             id = info['settings']['recipe'])
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
    job = js().call('/job/%s' % id)
    return show_build(id, job.get('latest_no', 0), 'latest', job)


@app.route('/<id>/success', methods = ['GET'])
def show_success(id):
    job = js().call('/job/%s' % id)
    return show_build(id, job.get('success_no', 0), 'success', job)


@app.route('/<id>/<int:build_no>', methods = ['GET'])
def show_build(id, build_no, active_tab = None, job = None):
    if not job:
        job = js().call('/job/%s' % id)
    info = js().call('/build/%s,%d' % (id, build_no))

    log = info['log']
    for l in log:
        l['dt'] = (l['t'] - log[0]['t']) / 1000
    log = simplify_log(log)

    return render_template('job_show.html',
                           id = id,
                           name = id,
                           active_tab = active_tab,
                           build = info['build'],
                           sessions = info['sessions'],
                           job = job,
                           log = log)


@app.route('/new', methods = ['GET'])
def show_new():
    return render_template('jobs_list.html')


@app.route('/', methods = ['GET'])
def index():
    jobs = js().call('/job')['jobs']
    jobs.sort(lambda a, b: cmp(a['id'], b['id']))
    return render_template('jobs_list.html',
                           jobs = jobs)
