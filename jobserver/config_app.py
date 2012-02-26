import web

from jobserver.gitdb import config, create_commit, update_head
from jobserver.gitdb import CommitException
from jobserver.webutils import abort, jsonify

urls = (
    '/(.+).json',           'PutConfig',
    '/(.+).txt',            'GetConfig',
)

config_app = web.application(urls, locals())


class PutConfig:
    def PUT(self, ref):
        repo = config()
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
        repo = config()
        sha1 = repo.refs['refs/heads/configs/%s' % ref]
        commit = repo.get_object(sha1)
        tree = repo.get_object(commit.tree)
        mode, sha = tree['config.py']
        b = repo.get_object(sha)
        return b.data
