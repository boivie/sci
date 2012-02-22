#!/usr/bin/env python
"""
    sci.jobserver
    ~~~~~~~~~~~~~

    Job Server

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
from optparse import OptionParser
import web, json, os, re, yaml, redis
import email.utils
from dulwich.repo import Repo
from dulwich.objects import Blob, Tree, Commit, parse_timezone
from time import time
from sci.utils import random_sha1

GIT_CONFIG = 'config.git'

STATE_STARTED = 'started'
STATE_DONE = 'done'
STATE_FAILED = 'failed'
STATE_ABORTED = 'aborted'

AUTHOR = 'SCI <sci@example.com>'

pool = redis.ConnectionPool(host='localhost', port=6379, db=0)


def get_ts():
    return int(time())


def conn():
    r = redis.StrictRedis(connection_pool=pool)
    return r


def get_gits():
    return [get_git(g) for g in [GIT_CONFIG]]


def get_git(git):
    return os.path.join(web.config._path, git)


def get_repo(git):
    return Repo(get_git(git))


class CommitException(Exception):
    pass


class NoChangesException(CommitException):
    pass


urls = (
    '/recipe/(.+).json',           'GetPutRecipe',
    '/metadata/(.+).json',         'GetPutMetadata',
    '/config/(.+).json',           'PutConfig',
    '/config/(.+).txt',            'GetConfig',
    '/job/(.+)',                   'GetPutJob',
    '/build/create/(.+).json',     'CreateBuild',

    # If the build ID is specified, we allow it to be updated
    '/build/B([0-9a-f]{40}).json', 'GetUpdateBuild',
    # If only the name+number is specified, read-only access
    '/build/(.+),([0-9]+)',        'GetBuild',

    '/slog',                       'AddLog',
    '/recipes',                    'ListRecipes',
    '/jobs',                       'ListJobs',
)

re_sha1 = re.compile('^([0-9a-f]{40})$')

app = web.application(urls, globals())


def is_sha1(ref):
    return re_sha1.match(ref)


def jsonify(**kwargs):
    web.header('Content-Type', 'application/json')
    return json.dumps(kwargs)


def abort(status, data):
    print("> %s" % data)
    raise web.webapi.HTTPError(status = status, data = data)


def create_commit(repo, files = None, tree = None, parent = None,
                  author = AUTHOR, message = "No message given"):
    object_store = repo.object_store
    if not tree:
        tree = Tree()
    for f in files:
        blob = Blob.from_string(f[2])
        object_store.add_object(blob)
        tree.add(f[0], f[1], blob.id)
    commit = Commit()
    if parent:
        commit.parents = [parent]
    else:
        commit.parents = []
    # Check that we have really updated the tree
    if parent:
        parent_commit = repo.get_object(parent)
        if parent_commit.tree == tree.id:
            raise NoChangesException()
    commit.tree = tree.id
    commit.author = commit.committer = author
    commit.commit_time = commit.author_time = get_ts()
    tz = parse_timezone('+0100')[0]
    commit.commit_timezone = commit.author_timezone = tz
    commit.encoding = "UTF-8"
    commit.message = message

    object_store.add_object(tree)
    object_store.add_object(commit)
    return commit


def update_head(repo, name, old_sha1, new_sha1):
    if not old_sha1:
        if not repo.refs.add_if_new(name, new_sha1):
            raise CommitException("Ref already exists")
    elif not repo.refs.set_if_equals(name, old_sha1, new_sha1):
        raise CommitException("Ref is not current")


class GetPutRecipe:
    def POST(self, name):
        input = json.loads(web.data())
        repo = get_repo(GIT_CONFIG)
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
        repo = get_repo(GIT_CONFIG)
        ref = get_recipe_ref(repo, name)
        commit = repo.get_object(ref)
        tree = repo.get_object(commit.tree)
        mode, sha = tree['build.py']
        data = repo.get_object(sha).data
        return jsonify(ref = ref,
                       contents = data,
                       metadata = get_recipe_metadata_from_blob(data))


def get_recipe_metadata_from_blob(contents):
    header = []
    for line in contents.splitlines():
        if line.startswith('#!/'):
            continue
        if not line or line[0] != '#':
            break

        header.append(line[1:])

    header = '\n'.join(header)
    return yaml.safe_load(header) or {}


def get_recipe_metadata(repo, name_or_sha1):
    ref = get_recipe_ref(repo, name_or_sha1)
    commit = repo.get_object(ref)
    tree = repo.get_object(commit.tree)
    mode, sha = tree['build.py']
    data = repo.get_object(sha).data
    metadata = get_recipe_metadata_from_blob(data)
    return metadata


class GetPutMetadata:
    def GET(self, name):
        repo = get_repo(GIT_CONFIG)
        return json.dumps(get_recipe_metadata(repo, name))


def get_recipe_ref(repo, name):
    # If it's a sha1, verify that it's correct
    if is_sha1(name):
        c = repo.get_object(name)
        assert c.type_name == 'commit'
        return name
    return repo.refs['refs/heads/recipes/%s' % name]


class PutConfig:
    def PUT(self, ref):
        repo = get_repo(GIT_CONFIG)
        old_rev = web.ctx.env.get('HTTP_X_PREV_REV')
        author = web.ctx.env.get('HTTP_X_AUTHOR',
                                 'Anonymous <anonymous@example.com>')
        commit = create_commit(repo, [('config.py', 0100755, web.data())],
                               parent = old_rev,
                               author = author,
                               message = 'Updated config')
        try:
            ref = 'refs/heads/configs/%s' % ref
            update_head(repo, ref, old_rev, commit.id)
            return jsonify(status = 'ok',
                           ref = commit.id)
        except CommitException as e:
            abort(412, str(e))


class GetConfig:
    def GET(self, ref):
        repo = get_repo(GIT_CONFIG)
        sha1 = repo.refs['refs/heads/configs/%s' % ref]
        commit = repo.get_object(sha1)
        tree = repo.get_object(commit.tree)
        mode, sha = tree['config.py']
        b = repo.get_object(sha)
        return b.data


def get_job(repo, name):
    if is_sha1(name):
        commit = repo.get_object(name)
    else:
        commit = repo.get_object(repo.refs['refs/heads/jobs/%s' % name])
    tree = repo.get_object(commit.tree)
    mode, sha = tree['job.yaml']
    obj = yaml.safe_load(repo.get_object(sha).data)
    return obj, commit.id


class GetPutJob:
    def POST(self, name):
        repo = get_repo(GIT_CONFIG)
        input = json.loads(web.data())
        job = input['contents']
        job['name'] = name

        while True:
            old = input.get('old')
            if name == 'private':
                try:
                    old = repo.refs['refs/heads/jobs/private']
                except KeyError:
                    old = None
            contents = yaml.safe_dump(job, default_flow_style = False)
            try:
                commit = create_commit(repo, [('job.yaml', 0100644, contents)],
                                       parent = old,
                                       message = "Updated Job")
            except NoChangesException:
                return jsonify(ref = old)

            try:
                update_head(repo, 'refs/heads/jobs/%s' % name, old, commit.id)
                return jsonify(ref = commit.id)
            except CommitException as e:
                if name != 'private':
                    abort(412, str(e))

    def GET(self, query):
        db = conn()
        results = {}
        parts = query.split(',')
        name = parts[0]
        repo = get_repo(GIT_CONFIG)
        results['settings'], results['ref'] = get_job(repo, name)
        results['stats'] = get_job_stats(db, name)

        return jsonify(**results)


KEY_JOB_INFO = 'job-%s'
KEY_BUILD_INFO = 'build-info:%s'
KEY_BUILD_ID = 'build-hash:%s:%d'

DEFAULT_EMPTY_JOB = dict(latest = dict(no = 0, ts = 0),
                         success = dict(no = 0, ts = 0))


def get_job_stats(db, name):
    info = db.get(KEY_JOB_INFO % name)
    if info:
        return json.loads(info)
    else:
        return DEFAULT_EMPTY_JOB


class CreateBuild:
    def POST(self, job_name):
        input = json.loads(web.data())
        # Verify that the job exists
        config = get_repo(GIT_CONFIG)

        if 'job_ref' in input:
            job, job_ref = get_job(config, input['job_ref'])
        else:
            job, job_ref = get_job(config, job_name)

        recipe_ref = job.get('recipe_ref')
        if not recipe_ref:
            recipe_ref = get_recipe_ref(config, job['recipe_name'])

        # Get a build number
        db = conn()
        key = KEY_JOB_INFO % job_name
        db.setnx(key, json.dumps(DEFAULT_EMPTY_JOB))
        now = get_ts()
        while True:
            try:
                with db.pipeline() as pipe:
                    pipe.watch(key)
                    info = json.loads(pipe.get(key))
                    number = info['latest']['no'] + 1
                    info['latest']['no'] = number
                    info['latest']['ts'] = now
                    pipe.multi()
                    pipe.set(key, json.dumps(info))
                    pipe.execute()
                    break
            except redis.WatchError:
                continue

        build_id = 'B%s' % random_sha1()
        build = dict(job_name = job['name'],
                     job_ref = job_ref,
                     recipe_name = job['recipe_name'],
                     recipe_ref = recipe_ref,
                     number = number,
                     state = STATE_STARTED,
                     created = email.utils.formatdate(now, localtime = True),
                     parameters = input.get('parameters', {}))
        db.set(KEY_BUILD_INFO % build_id[1:], json.dumps(build))
        db.set(KEY_BUILD_ID % (job_name, number), build_id)
        return jsonify(id = build_id, **build)


class GetUpdateBuild:
    def GET(self, build_id):
        db = conn()
        build = db.get(KEY_BUILD_INFO % build_id)
        if not build:
            abort(404, 'Invalid Build ID')
        build = json.loads(build)
        return jsonify(build = build)


class GetBuild:
    def GET(self, job_name, number):
        db = conn()
        number = int(number)
        build_id = db.get(KEY_BUILD_ID % (job_name, number))
        if build_id is None:
            abort(404, 'Not Found')
        build = db.get(KEY_BUILD_INFO % build_id)
        if not build:
            abort(404, 'Not Found')
        build = json.loads(build)
        return jsonify(build = build)


class ListRecipes:
    def GET(self):
        repo = get_repo(GIT_CONFIG)
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


class ListJobs:
    def GET(self):
        db = conn()
        repo = get_repo(GIT_CONFIG)
        jobs = []
        for name in repo.refs.keys():
            if not name.startswith('refs/heads/jobs/'):
                continue
            job, job_ref = get_job(repo, repo.refs[name])
            job_name = name[16:]
            info = get_job_stats(db, job_name)

            info['id'] = job_name
            info['recipe_name'] = job['recipe_name']
            if 'recipe_ref' in job:
                info['recipe_ref'] = job['recipe_ref']
            jobs.append(info)
        return jsonify(jobs = jobs)


class AddLog:
    def POST(self):
        print(web.data())
        return jsonify()


if __name__ == "__main__":
    parser = OptionParser()
    parser.add_option("-g", "--debug",
                      action = "store_true", dest = "debug", default = False,
                      help = "debug mode - will allow all requests")
    parser.add_option("-p", "--port", dest = "port", default = 6697,
                      help = "port to use")
    parser.add_option("--path", dest = "path", default = ".",
                      help = "path to use")

    (opts, args) = parser.parse_args()

    web.config._path = opts.path
    for git_path in get_gits():
        if not os.path.exists(git_path):
            print("Creating initial repository: %s" % git_path)
            os.makedirs(git_path)
            Repo.init_bare(git_path)

    web.httpserver.runsimple(app.wsgifunc(), ("0.0.0.0", int(opts.port)))
