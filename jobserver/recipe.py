import yaml

from jobserver.utils import is_sha1


def get_recipe_ref(repo, name):
    # If it's a sha1, verify that it's correct
    if is_sha1(name):
        c = repo.get_object(name)
        assert c.type_name == 'commit'
        return name
    return repo.refs['refs/heads/recipes/%s' % name]


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
