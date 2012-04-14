import yaml


def get_recipe_ref(repo, name, ref = None):
    if ref:
        c = repo.get_object(ref)
        assert c.type_name == 'commit'
        return ref
    return repo.refs['refs/heads/recipes/%s' % name]


def get_recipe_contents(repo, name, ref = None):
    ref = get_recipe_ref(repo, name, ref)
    commit = repo.get_object(ref)
    tree = repo.get_object(commit.tree)
    mode, sha = tree['build.py']
    data = repo.get_object(sha).data
    return ref, data


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


def get_recipe_metadata(repo, name, ref = None):
    ref, data = get_recipe_contents(repo, name, ref)
    metadata = get_recipe_metadata_from_blob(data)
    return metadata
