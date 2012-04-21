import sys
sys.path.append("../..")
from flask import Blueprint, render_template, url_for, request, redirect, abort
from sci.http_client import HttpClient, HttpError

app = Blueprint('recipes', __name__, template_folder='templates')


def c():
    return HttpClient('http://127.0.0.1:6697')


@app.route('/edit/<id>', methods = ['POST'])
def edit_post(id):
    try:
        c().call('/recipe/%s.json' % id,
                 input = dict(contents = request.form['contents'],
                              old = request.form['ref']))
    except HttpError as e:
        if e.code != 412:
            abort(500)
        else:
            pass
            # TODO
    return redirect(url_for('.show', id = id))


@app.route('/edit/<id>', methods = ['GET'])
def show_edit(id):
    recipe = c().call('/recipe/%s.json' % id)

    return render_template('recipes_edit.html',
                           recipe = recipe,
                           id = id,
                           active_tab = 'edit')


@app.route('/history/<id>', methods = ['GET'])
def show_history(id):
    pass


@app.route('/show/<id>', methods = ['GET'])
def show(id):
    recipe = c().call('/recipe/%s.json' % id)

    return render_template('recipes_show.html',
                           recipe = recipe,
                           active_tab = 'show',
                           id = id)


@app.route('/', methods = ['GET'])
def index():
    recipes = c().call('/recipe')['recipes']

    return render_template('recipes_list.html',
                           recipes = recipes)
