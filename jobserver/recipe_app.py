from flask import Blueprint, request, abort, jsonify, g

from jobserver.db import KEY_RECIPES
from jobserver.gitdb import create_commit, update_head
from jobserver.gitdb import NoChangesException, CommitException
from jobserver.recipe import get_recipe_metadata_from_blob
from jobserver.recipe import get_recipe_metadata, get_recipe_contents
from jobserver.recipe import get_recipe_history, update_recipe_cache

app = Blueprint('recipes', __name__)


@app.route('/', methods=['GET'])
def list_recipes():
    recipes = []
    for name in sorted(g.db.smembers(KEY_RECIPES)):
        metadata = get_recipe_metadata(g.repo, name)
        info = {'id': name,
                'description': metadata.get('Description', ''),
                'tags': metadata.get('Tags', [])}
        recipes.append(info)
    return jsonify(recipes = recipes)


@app.route('/<name>.json', methods=['POST'])
def do_post_recipe(name):
    contents = request.json['contents'].encode('utf-8')
    msg = request.json.get('commitmsg', '').encode('utf-8')
    msg = msg or "No message given"

    prev_ref, prev_contents = get_recipe_contents(g.db, name)

    while True:
        ref = request.json.get('old')
        if name == 'private':
            try:
                ref = g.repo.refs['refs/heads/recipes/private']
            except KeyError:
                ref = None

        try:
            commit = create_commit(g.repo,
                                   [('build.py', 0100755, contents)],
                                   parent = ref,
                                   message = msg)
        except NoChangesException:
            return jsonify(ref = ref)

        try:
            update_head(g.repo, 'refs/heads/recipes/%s' % name, ref, commit.id)
            break
        except CommitException:
            if name != 'private':
                abort(412, "Invalid Ref")
    update_recipe_cache(g.db, name, commit.id, contents, prev_contents)
    return jsonify(ref = commit.id)


@app.route('/<name>.json', methods=['GET'])
def do_get_recipe(name):
    ref, data = get_recipe_contents(g.repo, name,
                                    ref = request.args.get('ref'))
    return jsonify(ref = ref,
                   contents = data,
                   metadata = get_recipe_metadata_from_blob(data))


@app.route('/<name>/history.json', methods=['GET'])
def do_get_recipe_history(name):
    return jsonify(entries = get_recipe_history(g.repo, name))
