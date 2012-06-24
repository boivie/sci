from flask import Blueprint, request, abort, jsonify

from jobserver.gitdb import config, create_commit, update_head
from jobserver.gitdb import NoChangesException, CommitException
from jobserver.recipe import get_recipe_metadata_from_blob
from jobserver.recipe import get_recipe_metadata, get_recipe_contents
from jobserver.recipe import get_recipe_history

app = Blueprint('recipes', __name__)


@app.route('/', methods=['GET'])
def list_recipes():
    repo = config()
    recipes = []
    for name in repo.refs.keys():
        if not name.startswith('refs/heads/recipes/'):
            continue
        metadata = get_recipe_metadata(repo, name, repo.refs[name])
        info = {'id': name[19:],
                'description': metadata.get('Description', '')}
        if metadata.get('Tags'):
            info['tags'] = metadata['Tags']
        recipes.append(info)
    return jsonify(recipes = recipes)


@app.route('/<name>.json', methods=['POST'])
def do_post_recipe(name):
    repo = config()
    contents = request.json['contents'].encode('utf-8')
    msg = request.json.get('commitmsg', '').encode('utf-8')
    msg = msg or "No message given"
    while True:
        ref = request.json.get('old')
        if name == 'private':
            try:
                ref = repo.refs['refs/heads/recipes/private']
            except KeyError:
                ref = None

        try:
            commit = create_commit(repo,
                                   [('build.py', 0100755, contents)],
                                   parent = ref,
                                   message = msg)
        except NoChangesException:
            return jsonify(ref = ref)

        try:
            update_head(repo, 'refs/heads/recipes/%s' % name, ref, commit.id)
            return jsonify(ref = commit.id)
        except CommitException:
            if name != 'private':
                abort(412, "Invalid Ref")


@app.route('/<name>.json', methods=['GET'])
def do_get_recipe(name):
    repo = config()
    ref, data = get_recipe_contents(repo, name,
                                    ref = request.args.get('ref'))
    return jsonify(ref = ref,
                   contents = data,
                   metadata = get_recipe_metadata_from_blob(data))


@app.route('/<name>/history.json', methods=['GET'])
def do_get_recipe_history(name):
    repo = config()
    return jsonify(entries = get_recipe_history(repo, name))
