from flask import Blueprint, render_template, url_for, request, redirect, abort
from flask import current_app
from sci.http_client import HttpClient, HttpError

app = Blueprint('recipes', __name__, template_folder='templates')


def c():
    return HttpClient('http://' + current_app.config['JS_SERVER_NAME'])


@app.route('/create', methods = ['POST'])
def create_post():
    id = request.form['name']
    commitmsg = "Initial revision"
    contents = """\
# Description:
#    An empty recipe that does nothing right now

# Write your recipe here!
"""
    copyof = request.form['copyof'].strip()
    if copyof:
        copy = c().call('/recipe/%s.json' % copyof)
        contents = copy['contents']

    c().call('/recipe/%s.json' % id,
             input = dict(contents = contents,
                          commitmsg = commitmsg))
    return redirect(url_for('.show', id = id))


@app.route('/edit/<id>', methods = ['POST'])
def edit_post(id):
    try:
        c().call('/recipe/%s.json' % id,
                 input = dict(contents = request.form['contents'],
                              old = request.form['ref'],
                              commitmsg = request.form['commitmsg']))
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
                           id = id)


@app.route('/history/<id>', methods = ['GET'])
def show_history(id):
    info = c().call('/recipe/%s/history.json' % id)

    return render_template('recipes_history.html',
                           id = id,
                           entries = info['entries'])


@app.route('/show/<id>', methods = ['GET'])
def show(id):
    recipe = c().call('/recipe/%s.json' % id,
                      ref = request.args.get('ref'))

    return render_template('recipes_show.html',
                           recipe = recipe,
                           id = id)


@app.route('/', methods = ['GET'])
def index():
    recipes = c().call('/recipe/')['recipes']

    return render_template('recipes_list.html',
                           recipes = recipes)


@app.route('/create', methods = ['GET'])
def create():
    recipes = c().call('/recipe/')['recipes']

    return render_template('recipes_create.html',
                           recipes = recipes)
