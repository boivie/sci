from flask import Blueprint, request, render_template
from flask import current_app
from sci.http_client import HttpClient

app = Blueprint('search', __name__, template_folder='templates')


def js():
    return HttpClient('http://' + current_app.config['JS_SERVER_NAME'])


@app.route('', methods=['GET'])
def simple():
    q = request.args['q']
    result = js().call('/search/',
                       input = dict(q = q))

    return render_template('search.html',
                           q = q,
                           jobs = result['jobs'],
                           recipes = result['recipes'])
