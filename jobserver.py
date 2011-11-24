#!/usr/bin/env python
"""
    sci.jobserver
    ~~~~~~~~~~~~~

    Job Server

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
from optparse import OptionParser
import web, json, os, re
import email.utils
from dulwich.repo import Repo
from dulwich.objects import Blob, Tree, Commit, parse_timezone
from time import time

GIT_CONFIG = 'config.git'
GIT_BUILDS = 'builds.git'

STATE_STARTED = 'started'
STATE_DONE = 'done'
STATE_FAILED = 'failed'
STATE_ABORTED = 'aborted'

AUTHOR = 'SCI <sci@example.com>'


def get_gits():
    return [get_git(g) for g in [GIT_CONFIG, GIT_BUILDS]]


def get_git(git):
    return os.path.join(web.config._path, git)


def get_repo(git):
    return Repo(get_git(git))


class CommitException(Exception):
    pass

urls = (
    '/recipe/(.+).json',           'GetPutRecipe',
    '/config/(.+).json',           'PutConfig',
    '/config/(.+).txt',            'GetConfig',
    '/job/(.+).json',              'GetPutJob',
    '/build/create/(.+).json',     'CreateBuild',
    '/build/([0-9a-f]{40}).json',  'GetUpdateBuild',
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
    commit.tree = tree.id
    commit.author = commit.committer = author
    commit.commit_time = commit.author_time = int(time())
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

            commit = create_commit(repo,
                                   [('build.py', 0100755, contents)],
                                   parent = ref)
            try:
                update_head(repo, "refs/heads/recipes/%s" % name, ref, commit.id)
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
        return repo.get_object(sha).data


def get_recipe_ref(repo, name):
    # If it's a sha1, verify that it's correct
    if is_sha1(name):
        c = repo.get_object(name)
        assert c.type_name == 'commit'
        return name
    return repo.refs["refs/heads/recipes/%s" % name]


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
            ref = "refs/heads/configs/%s" % ref
            update_head(repo, ref, old_rev, commit.id)
            return jsonify(status = "ok",
                           ref = commit.id)
        except CommitException as e:
            abort(412, str(e))


class GetConfig:
    def GET(self, ref):
        repo = get_repo(GIT_CONFIG)
        sha1 = repo.refs["refs/heads/configs/%s" % ref]
        commit = repo.get_object(sha1)
        tree = repo.get_object(commit.tree)
        mode, sha = tree['config.py']
        b = repo.get_object(sha)
        return b.data


def get_job(repo, name):
    if is_sha1(name):
        commit = repo.get_object(name)
    else:
        commit = repo.get_object(repo.refs["refs/heads/jobs/%s" % name])
    tree = repo.get_object(commit.tree)
    mode, sha = tree['job.json']
    obj = json.loads(repo.get_object(sha).data)
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

            commit = create_commit(repo, [('job.json', 0100644, json.dumps(job))],
                                   parent = old,
                                   message = "Updated Job")
            try:
                update_head(repo, 'refs/heads/jobs/%s' % name, old, commit.id)
                return jsonify(ref = commit.id)
            except CommitException as e:
                if name != 'private':
                    abort(412, str(e))

    def GET(self, name):
        repo = get_repo(GIT_CONFIG)
        job, ref = get_job(repo, name)
        return jsonify(job = job, ref = ref)


class CreateBuild:
    def POST(self, name_or_sha1):
        # Verify that the job exists
        config = get_repo(GIT_CONFIG)
        builds = get_repo(GIT_BUILDS)
        job, job_ref = get_job(config, name_or_sha1)
        recipe_ref = get_recipe_ref(config, job["recipe"])

        while True:
            # Allocate a build number:
            try:
                cur_build_ref = builds.refs['refs/heads/%s' % job['name']]
                c = builds.get_object(cur_build_ref)
                tree = builds.get_object(c.tree)
                mode, latest_sha1 = tree['current.json']  # a link
                latest = builds.get_object(latest_sha1).data
                number = int(latest[:-5]) + 1
            except:
                cur_build_ref = None
                number = 1
                tree = None
            build = dict(job_name = job['name'],
                         number = number,
                         name = "%s-%d" % (job['name'], number),
                         state = STATE_STARTED,
                         created = email.utils.formatdate(localtime = True),
                         job_ref = job_ref,
                         recipe_ref = recipe_ref)
            fname = '%d.json' % number
            contents = json.dumps(build)
            commit = create_commit(builds,
                                   files = [(fname, 0100644, contents),
                                            ('current.json', 0120000, fname)],
                                   tree = tree,
                                   parent = cur_build_ref,
                                   message = "Create Build %s" % build['name'])
            try:
                ref = "refs/heads/%s" % job['name']
                update_head(builds, ref, cur_build_ref, commit.id)
                break
            except CommitException:
                pass  # re-iterate

        build['id'] = commit.id
        return jsonify(**build)


def find_build(build_id):
    # The ID is the commit where the build was added. That
    # will give us the full name and the number.
    repo = get_repo(GIT_BUILDS)
    commit = repo.get_object(build_id)
    tree = repo.get_object(commit.tree)
    mode, sha1 = tree['current.json']
    fname = repo.get_object(sha1).data
    mode, sha1 = tree[fname]
    create_obj = json.loads(repo.get_object(sha1).data)
    return create_obj["job_name"], create_obj["number"]


class GetUpdateBuild:
    def GET(self, build_id):
        repo = get_repo(GIT_BUILDS)
        job_name, number = find_build(build_id)

        cur_ref = repo.refs['refs/heads/%s' % job_name]
        commit = repo.get_object(cur_ref)
        tree = repo.get_object(commit.tree)
        mode, sha1 = tree['%d.json' % number]
        cur_obj = json.loads(repo.get_object(sha1).data)
        return jsonify(ref = cur_ref, build = cur_obj)

    def POST(self, build_id):
        repo = get_repo(GIT_BUILDS)
        job_name, number = find_build(build_id)
        input = json.loads(web.data())
        cur_ref = repo.refs['refs/heads/%s' % job_name]
        commit = repo.get_object(cur_ref)
        tree = repo.get_object(commit.tree)
        fname = '%s.json' % number
        contents = json.dumps(input['build'])
        commit = create_commit(repo,
                               tree = tree,
                               files = [(fname, 0100644, contents)],
                               message = "Updated %s-%d" % (job_name, number),
                               parent = cur_ref)
        try:
            ref = "refs/heads/%s" % job_name
            update_head(repo, ref, cur_ref, commit.id)
        except CommitException:
            abort(412, "Race condition")

        return jsonify(status = 'ok',
                       ref = commit.id)

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