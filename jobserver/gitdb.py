import os

from dulwich.repo import Repo
from dulwich.objects import Blob, Tree, Commit, parse_timezone

from jobserver.utils import get_ts

GIT_CONFIG = 'config.git'
AUTHOR = 'SCI <sci@example.com>'


class CommitException(Exception):
    pass


class NoChangesException(CommitException):
    pass


def config(path):
    return Repo(os.path.join(path, GIT_CONFIG))


def update_head(repo, name, old_sha1, new_sha1):
    if not old_sha1:
        if not repo.refs.add_if_new(name, new_sha1):
            raise CommitException("Ref already exists")
    elif not repo.refs.set_if_equals(name, old_sha1, new_sha1):
        raise CommitException("Ref is not current")


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
