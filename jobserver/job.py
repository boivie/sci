import yaml

KEY_JOB = 'job:%s'


def get_job(repo, name, ref = None):
    if ref:
        commit = repo.get_object(ref)
    else:
        commit = repo.get_object(repo.refs['refs/heads/jobs/%s' % name])
    tree = repo.get_object(commit.tree)
    mode, sha = tree['job.yaml']
    obj = yaml.safe_load(repo.get_object(sha).data)
    return obj, commit.id
