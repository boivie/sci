from flask import Blueprint, request, abort, jsonify, g

from jobserver.db import KEY_RECIPES
from jobserver.recipe import Recipe, RecipeNotCurrent, RecipeNotFound
from jobserver.utils import chunks

app = Blueprint('recipes', __name__)


@app.route('/', methods=['GET'])
def list_recipes():
    fields = ('#', 'recipe:*->tags', 'recipe:*->description')
    rows = [{'id': d[0], 'description': d[2],
             'tags': [t for t in d[1].split(',') if t]}
            for d in chunks(g.db.sort(KEY_RECIPES, get=fields), 3)]
    return jsonify(recipes = rows)


@app.route('/<name>.json', methods=['POST'])
def do_post_recipe(name):
    contents = request.json['contents'].encode('utf-8')
    msg = request.json.get('commitmsg', '').encode('utf-8')
    msg = msg or "No message given"

    recipe = Recipe.parse(name, contents)
    try:
        recipe.save(prev_ref = request.json.get('old'))
    except RecipeNotCurrent:
        abort(412)
    return jsonify(ref = recipe.ref)


@app.route('/<name>.json', methods=['GET'])
def do_get_recipe(name):
    try:
        recipe = Recipe.load(name, ref = request.args.get('ref'))
    except RecipeNotFound:
        abort(404)
    return jsonify(ref = recipe.ref,
                   contents = recipe.contents,
                   metadata = recipe.metadata)


@app.route('/<name>/history.json', methods=['GET'])
def do_get_recipe_history(name):
    return jsonify(entries = Recipe.get_edit_history(name))
