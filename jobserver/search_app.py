from flask import Blueprint, jsonify, g, request

from jobserver.db import KEY_TAG

app = Blueprint('search', __name__)


@app.route('/', methods=['POST'])
def simple():
    q = request.json['q']
    tokens = [word.strip().lower() for word in q.split()]
    tokens = [word for word in tokens if word]
    # Find jobs
    matches = g.db.sinter([KEY_TAG % w for w in tokens])
    jobs = [m[1:] for m in matches if m[0] == 'j']
    recipes = [m[1:] for m in matches if m[0] == 'r']
    return jsonify(jobs = jobs,
                   recipes = recipes)
