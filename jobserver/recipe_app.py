import json

import web

from jobserver.gitdb import config, create_commit, update_head
from jobserver.webutils import abort, jsonify
from jobserver.gitdb import NoChangesException, CommitException
from jobserver.recipe import get_recipe_metadata_from_blob
from jobserver.recipe import get_recipe_metadata, get_recipe_contents

urls = (
    '',                     'ListRecipes',
    '/(.+).json',           'GetPutRecipe',
)

recipe_app = web.application(urls, locals())


class ListRecipes:
    def GET(self):
        repo = config()
        recipes = []
        for name in repo.refs.keys():
            if not name.startswith('refs/heads/recipes/'):
                continue
            metadata = get_recipe_metadata(repo, repo.refs[name])
            info = {'id': name[19:],
                    'description': metadata.get('Description', '')}
            if metadata.get('Tags'):
                info['tags'] = metadata['Tags']
            recipes.append(info)
        return jsonify(recipes = recipes)


class GetPutRecipe:
    def POST(self, name):
        input = json.loads(web.data())
        repo = config()
        contents = input['contents'].encode('utf-8')

        while True:
            ref = input.get('old')
            if name == 'private':
                try:
                    ref = repo.refs['refs/heads/recipes/private']
                except KeyError:
                    ref = None

            try:
                commit = create_commit(repo,
                                       [('build.py', 0100755, contents)],
                                       parent = ref)
            except NoChangesException:
                return jsonify(ref = ref)

            try:
                update_head(repo, 'refs/heads/recipes/%s' % name, ref, commit.id)
                return jsonify(ref = commit.id)
            except CommitException:
                if name != 'private':
                    abort(412, "Invalid Ref")

    def GET(self, name):
        repo = config()
        ref, data = get_recipe_contents(repo, name)
        return jsonify(ref = ref,
                       contents = data,
                       metadata = get_recipe_metadata_from_blob(data))
