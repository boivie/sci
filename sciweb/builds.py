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


def show_settings(info, id):
    info['settings']['recipe_url'] = url_for('recipes.show',
                                             id = info['settings']['recipe_name'])
    return render_template('job_settings.html',
                           job_url = url_for('.show_job', id = id),
                           name = id,
                           active_tab = 'settings',
                           job = info)


def show_history(info, id):
    return "HISTORY"


def show_build(info, id, build_no, active_tab):
    if build_no != 0:
        build_info = js().call('/build/%s,%d' % (id, build_no))['build']
        build_info['job_url'] = url_for('.show_job', id = build_info['job_name'])
        build_info['recipe_url'] = url_for('recipes.show', id = build_info['recipe_name'])
    else:
        build_info = {}
    return render_template('job_show.html',
                           job_url = url_for('.show_job', id = id),
                           name = id,
                           build_no = build_no,
                           active_tab = active_tab,
                           job = info,
                           build = build_info)


@app.route('/show/<id>', methods = ['GET'])
def show_job(id):
    args = id.split(',')
    id = args[0]
    show = args[1] if len(args) > 1 else 'latest'

    info = js().call('/job/%s,queue,history' % id)
    if show == 'settings':
        return show_settings(info, id)
    if show == 'latest':
        return show_build(info, id, info['stats']['latest']['no'], 'latest')
    elif show == 'success':
        return show_build(info, id, info['stats']['success']['no'], 'success')
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
    jobs = js().call('/jobs')['jobs']
    for job in jobs:
        job['url'] = url_for('.show_job', id = job['id'])

    return render_template('jobs_list.html',
                           jobs = jobs)
