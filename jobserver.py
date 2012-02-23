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
from dulwich.repo import Repo
from dulwich.objects import Blob, Tree, Commit, parse_timezone
from time import time
from sci.utils import random_sha1
from sci.slog import JobBegun, JobDone, JobErrorThrown
from sci.queue import StartBuildQ

GIT_CONFIG = 'config.git'

STATE_PREPARED = 'prepared'
STATE_QUEUED = 'queued'
STATE_DISPATCHED = 'dispatched'
STATE_RUNNING = 'running'
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
    '/build/start/(.+)',           'StartBuild',

    # If the build ID is specified, we allow it to be updated
    '/build/B([0-9a-f]{40}).json', 'GetUpdateBuild',
    # If only the name+number is specified, read-only access
    '/build/(.+),([0-9]+)',        'GetBuild',

    '/slog/B([0-9a-f]{40})/S([0-9a-f]{40})',  'AddLog',
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


def get_job(repo, name, ref = None):
    if ref:
        commit = repo.get_object(ref)
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
        results['stats'] = db.hgetall(KEY_JOB % name)
        results['stats']['latest_no'] = int(results['stats']['latest_no'])
        return jsonify(**results)


KEY_JOB = 'job:%s'
KEY_BUILD = 'build:%s'
KEY_BUILD_ID = 'build-hash:%s:%d'
KEY_QUEUE = 'js:queue'


def queue(db, item, front = False):
    if front:
        db.lpush(KEY_QUEUE, item.serialize())
    else:
        db.rpush(KEY_QUEUE, item.serialize())


def new_build(db, job, job_ref, parameters = {},
              state = STATE_PREPARED):
    config = get_repo(GIT_CONFIG)
    recipe_ref = job.get('recipe_ref')
    if not recipe_ref:
        recipe_ref = get_recipe_ref(config, job['recipe_name'])

    # Get a build number
    now = get_ts()
    number = db.hincrby(KEY_JOB % job['name'], 'latest_no', 1)
    db.hset(KEY_JOB % job['name'], 'latest_ts', now)

    build_id = 'B%s' % random_sha1()
    build = dict(job_name = job['name'],
                 job_ref = job_ref,
                 recipe_name = job['recipe_name'],
                 recipe_ref = recipe_ref,
                 number = number,
                 state = state,
                 created = now,
                 session_id = 'S%s' % random_sha1(),
                 parameters = json.dumps(parameters))

    db.hmset(KEY_BUILD % build_id[1:], build)
    db.set(KEY_BUILD_ID % (job['name'], number), build_id)
    return build_id, build


class CreateBuild:
    def POST(self, job_name):
        db = conn()
        config = get_repo(GIT_CONFIG)
        data = web.data()
        input = json.loads(data) if data else {}

        job, job_ref = get_job(config, job_name, input.get('job_ref'))
        build_id, build = new_build(db, job, job_ref,
                                    input.get('parameters', {}))

        return jsonify(id = build_id, **build)


class StartBuild:
    def POST(self, job_name):
        db = conn()
        config = get_repo(GIT_CONFIG)
        data = web.data()
        input = json.loads(data) if data else {}

        job, job_ref = get_job(config, job_name, input.get('job_ref'))
        build_id, build = new_build(db, job, job_ref,
                                    input.get('parameters', {}),
                                    state = STATE_QUEUED)

        queue(db, StartBuildQ(build_id, build['session_id']))
        return jsonify(id = build_id, **build)


def get_build_info(db, build_id):
        build = db.hgetall(KEY_BUILD % build_id)
        if not build:
            return None
        build['number'] = int(build['number'])
        build['parameters'] = json.loads(build['parameters'])
        return build


class GetUpdateBuild:
    def GET(self, build_id):
        build = get_build_info(conn(), build_id)
        if not build:
            abort(404, 'Invalid Build ID')
        return jsonify(build = build)


class GetBuild:
    def GET(self, job_name, number):
        db = conn()
        number = int(number)
        build_id = db.get(KEY_BUILD_ID % (job_name, number))
        if build_id is None:
            abort(404, 'Not Found')
        build_id = build_id[1:]
        build = get_build_info(db, build_id)
        if not build:
            abort(404, 'Invalid Build ID')

        log = {}
        sessions = db.smembers(KEY_BUILD_SESSIONS % build_id)
        for session_id in sessions:
            log[session_id] = db.lrange(KEY_SLOG % (build_id, session_id),
                                        0, 1000)
        return jsonify(build = build,
                       log = log)


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
            job_name = name[16:]
            job, job_ref = get_job(repo, job_name, repo.refs[name])

            info = db.hgetall(KEY_JOB % job_name)
            info['id'] = job_name
            info['recipe_name'] = job['recipe_name']
            if 'recipe_ref' in job:
                info['recipe_ref'] = job['recipe_ref']
            jobs.append(info)
        return jsonify(jobs = jobs)


KEY_BUILD_SESSIONS = 'build-sessions:%s'
KEY_SLOG = 'build-slog:%s:%s'


def DoJobDone(db, build_id, li):
    db.hset(KEY_BUILD % build_id, 'state', STATE_DONE)


def DoJobErrorThrown(db, build_id, li):
    db.hset(KEY_BUILD % build_id, 'state', STATE_FAILED)


def DoJobBegun(db, build_id, li):
    db.hset(KEY_BUILD % build_id, 'state', STATE_RUNNING)


SLOG_HANDLERS = {JobBegun.type: DoJobBegun,
                 JobDone.type: DoJobDone,
                 JobErrorThrown.type: DoJobErrorThrown}


class AddLog:
    def POST(self, build_id, session_id):
        # Verify that the build id exists.
        db = conn()
        if not db.exists(KEY_BUILD % build_id):
            abort(404, 'Invalid Build ID')
        db.sadd(KEY_BUILD_SESSIONS % build_id, session_id)
        data = web.data()
        db.rpush(KEY_SLOG % (build_id, session_id), data)
        li = json.loads(data)
        try:
            handler = SLOG_HANDLERS[li['type']]
        except KeyError:
            pass
        else:
            handler(db, build_id, li)

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
