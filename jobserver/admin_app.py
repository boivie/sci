from flask import Blueprint, g
import yaml

from jobserver.db import KEY_RECIPES, KEY_JOBS, KEY_TAG
from jobserver.db import KEY_JOB, KEY_RECIPE
from jobserver.job import get_job_uncached
from jobserver.recipe import get_recipe_uncached
from jobserver.recipe import get_recipe_metadata_from_blob

app = Blueprint('admin', __name__)


@app.route('/rebuild_caches', methods=['POST'])
def rebuild_caches():
    tag_keys = g.db.keys(KEY_TAG % "*")
    with g.db.pipeline() as pipe:
        pipe.delete(KEY_RECIPES)
        pipe.delete(KEY_JOBS)
        for k in g.db.keys(KEY_TAG % "*"):
            pipe.delete(k)

        for tag_key in tag_keys:
            pipe.delete(tag_key)

        jobs = [r[16:] for r in g.repo.refs.keys()
                if r.startswith('refs/heads/jobs')]
        for name in jobs:
            yaml_str, dbref = get_job_uncached(name)
            job = yaml.safe_load(yaml_str)
            for tag in job.get('tags', []):
                pipe.sadd(KEY_TAG % tag, 'j' + name)
            pipe.hset(KEY_JOB % name, 'yaml', yaml_str)
            pipe.hset(KEY_JOB % name, 'description',
                      job.get('description', ''))
            pipe.hset(KEY_JOB % name, 'tags',
                      ",".join(job.get('tags', '')))
            pipe.hset(KEY_JOB % name, 'sha1', dbref)
            pipe.sadd(KEY_JOBS, name)

        recipes = [r[19:] for r in g.repo.refs.keys()
                   if r.startswith('refs/heads/recipes')]
        for name in recipes:
            dbref, contents = get_recipe_uncached(g.repo, name)
            meta = get_recipe_metadata_from_blob(contents)
            for tag in meta.get('Tags', []):
                pipe.sadd(KEY_TAG % tag, 'r' + name)
            pipe.hset(KEY_RECIPE % name, 'contents', contents)
            pipe.hset(KEY_RECIPE % name, 'description',
                      meta.get('Description', ''))
            pipe.hset(KEY_RECIPE % name, 'tags',
                      ",".join(meta.get('Tags', '')))
            pipe.hset(KEY_RECIPE % name, 'sha1', dbref)
            pipe.sadd(KEY_RECIPES, name)

        pipe.execute()
    return "done\n"
