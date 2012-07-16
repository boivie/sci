import json

from flask import g
import yaml

from jobserver.db import KEY_RECIPE, KEY_RECIPES, KEY_TAG
from jobserver.gitdb import create_commit, update_head
from jobserver.gitdb import NoChangesException, CommitException


class RecipeParseError(Exception):
    pass


class RecipeNotFound(Exception):
    pass


class RecipeNotCurrent(Exception):
    pass


class Recipe(object):
    def __init__(self, name, metadata, contents = None, ref = None):
        self._name = name
        self._obj = metadata
        self._contents = contents
        self._ref = ref

    @property
    def name(self):
        return self._name

    @property
    def ref(self):
        return self._ref

    @property
    def metadata(self):
        return self._obj

    @property
    def tags(self):
        return self._obj.get('Tags', [])

    @property
    def description(self):
        return self._obj.get('Description', '')

    @property
    def parameters(self):
        return self._obj.get('Parameters', {})

    @property
    def contents(self):
        return self._contents

    def save(self, prev_ref = None, message = None):
        message = message or "Updated Recipe"

        if self.name == 'private':
            try:
                prev_ref = g.repo.refs['refs/heads/recipes/private']
            except KeyError:
                prev_ref = None

        try:
            commit = create_commit(g.repo, [('build.py', 0100644, self.contents)],
                                   parent = prev_ref,
                                   message = message)
            self._ref = commit.id
        except NoChangesException:
            return
        try:
            update_head(g.repo, 'refs/heads/recipes/%s' % self.name,
                        prev_ref, commit.id)
        except CommitException:
            if self.name == 'private':
                return self.save(prev_ref, message)
            raise RecipeNotCurrent()
        self._update_cache()

    def _update_cache(self):
        # TODO: Still a race condition if a newer edit updates the cache
        # before an older manages to do it.
        key = KEY_RECIPE % self.name

        def update(pipe):
            try:
                prev = Recipe.load(self.name, pipe = pipe)
                prev_tags = set(prev.tags)
            except RecipeNotFound:
                prev_tags = set()
            cur_tags = set(self.tags)

            pipe.multi()
            for tag in prev_tags - cur_tags:
                pipe.srem(KEY_TAG % tag, 'r' + self.name)
            for tag in cur_tags - prev_tags:
                pipe.sadd(KEY_TAG % tag, 'r' + self.name)
            pipe.hset(key, 'json', json.dumps(self._obj))
            pipe.hset(key, 'contents', self.contents)
            pipe.hset(key, 'description', self.description)
            pipe.hset(key, 'tags', ','.join(self.tags))
            pipe.hset(key, 'sha1', self.ref)
            pipe.sadd(KEY_RECIPES, self.name)

        g.db.transaction(update, key)

    @classmethod
    def _extract_metadata(cls, contents):
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

    @classmethod
    def parse(cls, name, contents, ref = None):
        try:
            obj = Recipe._extract_metadata(contents)
        except Exception as e:
            raise RecipeParseError(e)
        tags = [t.strip().lower() for t in obj.get('Tags', [])]
        if '' in tags:
            tags.remove('')
        obj.pop('Tags', None)
        if tags:
            obj['Tags'] = tags
        return Recipe(name, obj, contents, ref)

    @classmethod
    def load(cls, name, ref = None, pipe = None):
        if not pipe:
            pipe = g.db
        obj, contents, dbref = pipe.hmget(KEY_RECIPE % name, ('json', 'contents', 'sha1'))
        if dbref is None or (ref and ref != dbref):
            contents, dbref = cls._get_from_archive(name, ref)
            if not dbref:
                raise RecipeNotFound()
            return Recipe.parse(name, contents, dbref)
        if not dbref:
            raise RecipeNotFound()
        return Recipe(name, json.loads(obj), contents, ref = dbref)

    @classmethod
    def _get_from_archive(cls, name, ref = None):
        if not ref:
            try:
                ref = g.repo.refs['refs/heads/recipes/%s' % name]
            except KeyError:
                return None, None
        commit = g.repo.get_object(ref)
        tree = g.repo.get_object(commit.tree)
        mode, sha = tree['build.py']
        return g.repo.get_object(sha).data, commit.id

    @classmethod
    def get_edit_history(cls, name, limit = 20):
        entries = []
        ref = g.repo.refs['refs/heads/recipes/%s' % name]
        for i in range(limit):
            c = g.repo.get_object(ref)
            entries.append({'ref': ref,
                            'msg': c.message.splitlines()[0],
                            'date': c.commit_time,
                            'by': c.committer})
            try:
                ref = c.parents[0]
            except IndexError:
                break
        return entries
