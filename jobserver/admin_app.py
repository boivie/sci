from flask import Blueprint, g
import json

from jobserver.db import KEY_RECIPES, KEY_JOBS, KEY_TAG
from jobserver.db import KEY_JOB, KEY_RECIPE
from jobserver.job import Job
from jobserver.recipe import Recipe

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
            yaml_str, dbref = Job._get_from_archive(name)
            job = Job.parse(name, yaml_str, dbref)
            for tag in job.tags:
                pipe.sadd(KEY_TAG % tag, 'j' + name)
            pipe.hset(KEY_JOB % name, 'yaml', yaml_str)
            pipe.hset(KEY_JOB % name, 'json', json.dumps(job._obj))
            pipe.hset(KEY_JOB % name, 'description', job.description)
            pipe.hset(KEY_JOB % name, 'tags', ",".join(job.tags))
            pipe.hset(KEY_JOB % name, 'sha1', dbref)
            pipe.sadd(KEY_JOBS, name)

        recipes = [r[19:] for r in g.repo.refs.keys()
                   if r.startswith('refs/heads/recipes')]
        for name in recipes:
            contents, dbref = Recipe._get_from_archive(name)
            recipe = Recipe.parse(name, contents, dbref)
            for tag in recipe.tags:
                pipe.sadd(KEY_TAG % tag, 'r' + name)
            pipe.hset(KEY_RECIPE % name, 'contents', recipe.contents)
            pipe.hset(KEY_RECIPE % name, 'json', json.dumps(recipe.metadata))
            pipe.hset(KEY_RECIPE % name, 'description', recipe.description)
            pipe.hset(KEY_RECIPE % name, 'tags', ",".join(recipe.tags))
            pipe.hset(KEY_RECIPE % name, 'sha1', dbref)
            pipe.sadd(KEY_RECIPES, name)

        pipe.execute()
    return "done\n"
