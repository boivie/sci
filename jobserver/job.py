import yaml
from jobserver.recipe import get_recipe_metadata


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


def merge_job_parameters(repo, job):
    params = {}
    recipe = get_recipe_metadata(repo, job['recipe_name'], job.get('recipe_ref'))

    for k, v in recipe['Parameters'].iteritems():
        v['name'] = k
        params[k] = v

    # and override by the job's
    for k, v in job.get('parameters', {}).iteritems():
        for k2, v2 in v.iteritems():
            params[k][k2] = v2
    return params
