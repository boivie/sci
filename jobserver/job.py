import json

from flask import g
import yaml
from jobserver.recipe import get_recipe_metadata
from jobserver.db import KEY_JOB, KEY_JOBS, KEY_TAG
from jobserver.build import KEY_JOB_BUILDS, KEY_BUILD
from jobserver.gitdb import create_commit, update_head
from jobserver.gitdb import NoChangesException, CommitException


class JobParseError(Exception):
    pass


class JobNotFound(Exception):
    pass


class JobNotCurrent(Exception):
    pass


class Job(object):
    def __init__(self, name, obj, yaml_str = None, ref = None):
        self._name = name
        self._obj = obj
        self._yaml_str = yaml_str
        self._ref = ref

    @property
    def name(self):
        return self._name

    @property
    def yaml(self):
        if self._yaml_str is None:
            self._yaml_str = Job._get_yaml(self._name, self._ref)
        return self._yaml_str

    @property
    def ref(self):
        return self._ref

    @property
    def tags(self):
        return self._obj.get('tags', [])

    @property
    def description(self):
        return self._obj.get('description', '')

    @property
    def recipe(self):
        return self._obj['recipe']

    @property
    def recipe_ref(self):
        return self._obj.get('recipe_ref') or None

    @property
    def parameters(self):
        return self._obj.get('parameters', {})

    @property
    def last_success(self):
        bid = g.db.hget(KEY_JOB % self.name, 'success')
        if not bid:
            return 0
        return int(g.db.hget(KEY_BUILD % bid, 'number'))

    @property
    def latest_build(self):
        return g.db.llen(KEY_JOB_BUILDS % self.name) or 0

    def save(self, prev_ref = None, message = None):
        message = message or "Updated Job"

        if self.name == 'private':
            try:
                prev_ref = g.repo.refs['refs/heads/jobs/private']
            except KeyError:
                prev_ref = None

        try:
            commit = create_commit(g.repo, [('job.yaml', 0100644, self.yaml)],
                                   parent = prev_ref,
                                   message = message)
            self._ref = commit.id
        except NoChangesException:
            return
        try:
            update_head(g.repo, 'refs/heads/jobs/%s' % self.name,
                        prev_ref, commit.id)
        except CommitException:
            if self.name == 'private':
                return self.save(prev_ref, message)
            raise JobNotCurrent()
        self._update_cache()

    def _update_cache(self):
        # TODO: Still a race condition if a newer edit updates the cache
        # before an older manages to do it.
        key = KEY_JOB % self.name

        def update(pipe):
            try:
                prev = Job.load(self.name, pipe = pipe)
                prev_tags = set(prev.tags)
            except JobNotFound:
                prev_tags = set()
            cur_tags = set(self.tags)

            pipe.multi()
            for tag in prev_tags - cur_tags:
                pipe.srem(KEY_TAG % tag, 'j' + self.name)
            for tag in cur_tags - prev_tags:
                pipe.sadd(KEY_TAG % tag, 'j' + self.name)
            pipe.hset(key, 'json', json.dumps(self._obj))
            pipe.hset(key, 'yaml', self.yaml)
            pipe.hset(key, 'description', self.description)
            pipe.hset(key, 'tags', ','.join(self.tags))
            pipe.hset(key, 'sha1', self.ref)
            pipe.sadd(KEY_JOBS, self.name)

        g.db.transaction(update, key)

    def get_merged_params(self):
        params = {}
        recipe = get_recipe_metadata(g.repo, self.recipe, self.recipe_ref)

        for k, v in recipe['Parameters'].iteritems():
            v['name'] = k
            params[k] = v

        # and override by the job's
        for k, v in self.parameters.iteritems():
            for k2, v2 in v.iteritems():
                params[k][k2] = v2
        return params

    @classmethod
    def parse(cls, name, yaml_str, ref = None):
        try:
            obj = yaml.safe_load(yaml_str)
        except:
            return JobParseError()
        # Clean the job a bit.
        obj['recipe'] = obj['recipe'].strip()
        rref = obj.get('recipe_ref', '').strip()
        obj.pop('recipe_ref', None)
        if rref:
            obj['recipe_ref'] = rref
        tags = [t.strip().lower() for t in obj.get('tags', [])]
        if '' in tags:
            tags.remove('')
        obj.pop('tags', None)
        if tags:
            obj['tags'] = tags
        obj['name'] = name
        return Job(name, obj, yaml_str, ref)

    @classmethod
    def load(cls, name, ref = None, pipe = None):
        if not pipe:
            pipe = g.db
        job, dbref = pipe.hmget(KEY_JOB % name, ('json', 'sha1'))
        if dbref is None or (ref and ref != dbref):
            yaml_str, dbref = cls._get_from_archive(name, ref)
            if not dbref:
                raise JobNotFound()
            return Job.parse(name, yaml_str, dbref)
        if not dbref:
            raise JobNotFound()
        return Job(name, json.loads(job), ref = dbref)

    @classmethod
    def _get_yaml(cls, name, ref):
        assert(ref != None)
        yaml_str, dbref = g.db.hmget(KEY_JOB % name, ('yaml', 'sha1'))
        if dbref is None or (ref != dbref):
            yaml_str, dbref = cls._get_from_archive(name, ref)
            assert(dbref != None)
        return yaml_str

    @classmethod
    def _get_from_archive(cls, name, ref = None):
        if not ref:
            try:
                ref = g.repo.refs['refs/heads/jobs/%s' % name]
            except KeyError:
                return None, None
        commit = g.repo.get_object(ref)
        tree = g.repo.get_object(commit.tree)
        mode, sha = tree['job.yaml']
        return g.repo.get_object(sha).data, commit.id
