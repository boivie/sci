from flask import Blueprint, render_template, url_for, request, redirect, abort
from flask import current_app, make_response, jsonify
import yaml

from sci.http_client import HttpClient, HttpError

app = Blueprint('builds', __name__, template_folder='templates')


def js():
    return HttpClient('http://' + current_app.config['JS_SERVER_NAME'])


@app.route('/<id>/edit', methods = ['POST'])
def edit(id):
    old = request.form['ref']
    # Only manipulate the fields we can change in the UI
    info = js().call('/job/%s' % id, old = old, yaml=1)
    job = yaml.safe_load(info['yaml'])
    job['description'] = request.form['description']
    job['recipe'] = request.form['recipe']
    job['recipe_ref'] = request.form.get('recipe_ref', '')
    job['tags'] = request.form['tags'].split(',')
    params = {}
    for name in [n for n in request.form.keys() if n.startswith("param_")]:
        pname = name[6:]
        params[pname] = {'default': request.form[name],
                         'required': False}
    job['parameters'] = params
    try:
        js().call('/job/%s/raw' % id,
                  input = dict(yaml = yaml.safe_dump(job),
                               old = old))
    except HttpError as e:
        if e.code != 412:
            abort(500)
        else:
            pass
            # TODO
    return redirect(url_for('.show_home', id = id))


@app.route('/<id>/raw_edit', methods = ['POST'])
def raw_edit(id):
    try:
        js().call('/job/%s/raw' % id,
                  input = dict(yaml = request.form['yaml'],
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
    job = js().call('/job/%s' % id, yaml = 1)
    return render_template('job_edit_raw.html',
                           id = id,
                           job = job)


@app.route('/<id>/edit', methods = ['GET'])
def show_edit(id):
    recipes = js().call('/recipe/')['recipes']

    job = js().call('/job/%s' % id)
    params = job['merged_params']
    for k, v in params.iteritems():
        # 'default' doesn't play well in jquery.tmpl - why?
        if 'default' in v:
            v['def'] = v['default']
            del v['default']

    params = params.values()
    params.sort(lambda a, b: cmp(a['name'], b['name']))

    return render_template('job_edit.html',
                           id = id,
                           params = params,
                           job = job,
                           recipes = recipes)


@app.route('/<id>/edit-history', methods = ['GET'])
def show_edit_history(id):
    return "TODO"


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
    return redirect(url_for('.show_log', id = id, build_no = info['number']))


@app.route('/<id>/start', methods = ['GET'])
def show_start(id):
    job = js().call('/job/%s' % id)
    params = job['merged_params']
    for k, v in params.iteritems():
        # 'default' doesn't play well in jquery.tmpl - why?
        if 'default' in v:
            v['def'] = v['default']
            del v['default']

    params = params.values()
    params.sort(lambda a, b: cmp(a['name'], b['name']))

    return render_template('job_start.html',
                           id = id,
                           params = params,
                           job = job)


@app.route('/<id>/home', methods = ['GET'])
@app.route('/<id>', methods = ['GET'])
def show_home(id):
    job = js().call('/job/%s' % id)
    return render_template('job_settings.html',
                           id = id,
                           job = job)


@app.route('/<id>/history', methods = ['GET'])
def show_history(id):
    job = js().call('/job/%s' % id, history = 1)
    return render_template('job_history.html',
                           id = id,
                           job = job)


@app.route('/<id>/latest', methods = ['GET'])
def show_latest(id):
    job = js().call('/job/%s' % id)
    return show_build(id, job['latest_no'], job)


@app.route('/<id>/success', methods = ['GET'])
def show_success(id):
    job = js().call('/job/%s' % id)
    return show_build(id, job['success_no'], job)


@app.route('/<id>/<int:build_no>/log', methods = ['GET'])
def show_log(id, build_no):
    job = js().call('/job/%s' % id)
    info = js().call('/build/%s,%d' % (id, build_no))

    resp = render_template('build_log.html',
                           id = id,
                           build = info['build'],
                           sessions = info['sessions'],
                           uuid = info['uuid'],
                           job = job)
    resp = make_response(resp)
    resp.headers['Access-Control-Allow-Origin'] = '*'
    return resp


@app.route('/<build_uuid>/progress.json', methods = ['GET'])
def build_progress(build_uuid):
    start = request.args.get('start')
    if start:
        ret = js().call('/build/%s/progress' % build_uuid, start = start)
    else:
        ret = js().call('/build/%s/progress' % build_uuid)
    return jsonify(**ret)


@app.route('/<id>/<int:build_no>', methods = ['GET'])
def show_build(id, build_no, job = None):
    if not job:
        job = js().call('/job/%s' % id)
    info = js().call('/build/%s,%d' % (id, build_no))

    return render_template('build_overview.html',
                           id = id,
                           build = info['build'],
                           job = job,
                           sessions = info['sessions'])


@app.route('/new', methods = ['POST'])
def new():
    id = request.form['name'].strip()
    js().call('/job/%s/create' % id,
              input = dict(recipe = request.form['recipe']))
    return redirect(url_for('.show_edit', id = id))


@app.route('/new', methods = ['GET'])
def show_new():
    recipes = js().call('/recipe/')['recipes']
    return render_template('job_create.html',
                           recipes = recipes)


@app.route('/', methods = ['GET'])
def index():
    jobs = js().call('/job/')['jobs']
    jobs.sort(lambda a, b: cmp(a['id'], b['id']))
    return render_template('jobs_list.html',
                           jobs = jobs)
