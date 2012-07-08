from flask import g
import yaml

from jobserver.db import KEY_RECIPE, KEY_RECIPES, KEY_TAG


def get_recipe_ref(repo, name, ref = None):
    if ref:
        c = repo.get_object(ref)
        assert c.type_name == 'commit'
        return ref
    return repo.refs['refs/heads/recipes/%s' % name]


def get_recipe_uncached(repo, name, ref = None):
    dbref = get_recipe_ref(repo, name, ref)
    commit = repo.get_object(dbref)
    tree = repo.get_object(commit.tree)
    mode, sha = tree['build.py']
    return dbref, repo.get_object(sha).data


def get_recipe_contents(repo, name, ref = None, use_cache = True):
    dbref, data = g.db.hmget(KEY_RECIPE % name, 'sha1', 'contents')
    if not use_cache or dbref is None or (ref and dbref != ref):
        return get_recipe_uncached(repo, name, ref)
    return dbref, data


def get_recipe_metadata_from_blob(contents):
    header = []
    for line in contents.splitlines():
        if line.startswith('#!/'):
            continue
        if not line or line[0] != '#':
            break

        header.append(line[1:])

    header = '\n'.join(header)
    metadata = yaml.safe_load(header) or {}
    if not isinstance(metadata, dict):
        metadata = {}
    return metadata


def get_recipe_metadata(repo, name, ref = None):
    ref, data = get_recipe_contents(repo, name, ref)
    metadata = get_recipe_metadata_from_blob(data)
    return metadata


def get_recipe_history(repo, name, limit = 20):
    entries = []
    ref = get_recipe_ref(repo, name)
    for i in range(limit):
        c = repo.get_object(ref)
        entries.append({'ref': ref,
                        'msg': c.message.splitlines()[0],
                        'date': c.commit_time,
                        'by': c.committer})
        try:
            ref = c.parents[0]
        except IndexError:
            break
    return entries


def update_recipe_cache(db, name, ref, contents, prev_contents):
    # TODO: Make this transactional using 'WATCH'
    cur_meta = get_recipe_metadata_from_blob(contents)
    prev_meta = get_recipe_metadata_from_blob(prev_contents)
    prev_tags = set(prev_meta.get('Tags', []))
    cur_tags = set(cur_meta.get('Tags', []))

    with db.pipeline() as pipe:
        for tag in prev_tags - cur_tags:
            pipe.srem(KEY_TAG % tag, 'r' + name)
        for tag in cur_tags - prev_tags:
            pipe.sadd(KEY_TAG % tag, 'r' + name)
        pipe.hset(KEY_RECIPE % name, 'contents', contents)
        pipe.hset(KEY_RECIPE % name, 'sha1', ref)
        pipe.sadd(KEY_RECIPES, name)
        pipe.execute()
