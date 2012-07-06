from flask import g
import yaml
from jobserver.recipe import get_recipe_metadata
from jobserver.db import KEY_JOB, KEY_JOBS, KEY_TAG


def get_job(db, name, ref = None, raw = False):
    yaml_str, dbref = db.hmget(KEY_JOB % name, ('yaml', 'sha1'))
    if dbref is None or (ref and ref != dbref):
        if not ref:
            try:
                ref = g.repo.refs['refs/heads/jobs/%s' % name]
            except KeyError:
                return None, None
        commit = g.repo.get_object(ref)
        dbref = commit.id
        tree = g.repo.get_object(commit.tree)
        mode, sha = tree['job.yaml']
        yaml_str = g.repo.get_object(sha).data

    if raw:
        return yaml_str, dbref
    return yaml.safe_load(yaml_str), dbref


def merge_job_parameters(repo, job):
    params = {}
    recipe = get_recipe_metadata(repo, job['recipe'], job.get('recipe_ref'))

    for k, v in recipe['Parameters'].iteritems():
        v['name'] = k
        params[k] = v

    # and override by the job's
    for k, v in job.get('parameters', {}).iteritems():
        for k2, v2 in v.iteritems():
            params[k][k2] = v2
    return params


def update_job_cache(db, name, sha1, contents, prev_contents):
    prev_job = yaml.safe_load(prev_contents) if prev_contents else {}
    cur_job = yaml.safe_load(contents)
    prev_tags = set(prev_job.get('tags', []))
    cur_tags = set(cur_job.get('tags', []))

    with db.pipeline() as pipe:
        for tag in prev_tags - cur_tags:
            pipe.srem(KEY_TAG % tag, name)
        for tag in cur_tags - prev_tags:
            pipe.sadd(KEY_TAG % tag, name)
        pipe.hset(KEY_JOB % name, 'yaml', contents)
        pipe.hset(KEY_JOB % name, 'sha1', sha1)
        pipe.sadd(KEY_JOBS, name)
        pipe.execute()
