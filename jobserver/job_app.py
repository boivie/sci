import types

from flask import Blueprint, request, jsonify, abort
import yaml

from jobserver.db import conn
from jobserver.gitdb import config, create_commit, update_head
from jobserver.gitdb import NoChangesException, CommitException
from jobserver.job import get_job, KEY_JOB, merge_job_parameters
from jobserver.build import KEY_BUILD, KEY_JOB_BUILDS, KEY_SESSION

app = Blueprint('job', __name__)


@app.route('/<name>', methods=['POST'])
def put_job(name):
    repo = config()
    job = request.json['contents']
    if type(job) is not types.DictType:
        job = yaml.safe_load(job)

    # Clean the job a bit.
    rref = job.get('recipe_ref', '').strip()
    job.pop('recipe_ref', None)
    if rref:
        job['recipe_ref'] = rref
    tags = [t.strip() for t in job.get('tags', [])]
    if '' in tags:
        tags.remove('')
    job.pop('tags', None)
    if tags:
        job['tags'] = tags
    job['name'] = name

    while True:
        old = request.json.get('old')
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


@app.route('/<query>', methods=['GET'])
def do_get_job(query):
    db = conn()
    results = {}
    parts = query.split(',')
    name = parts[0]
    ref = None
    if '@' in name:
        name, ref = name.split('@')
    repo = config()
    if request.args.get('show') == 'raw':
        results['settings'], results['ref'] = get_job(repo, name, ref, True)
        return jsonify(**results)
    else:
        results['settings'], results['ref'] = get_job(repo, name, ref)
    success_bid = db.hget(KEY_JOB % name, 'success')
    if success_bid:
        success_no = db.hget(KEY_BUILD % success_bid, 'number')
        results['success_no'] = int(success_no)
        results['latest_no'] = db.llen(KEY_JOB_BUILDS % name)
    # Fetch information about the latest 10 builds
    history = []
    build_keys = ('number', 'created', 'description', 'build_id')
    session_keys = ('state', 'result')
    for build_id in db.lrange(KEY_JOB_BUILDS % name, -30, -1):
        number, created, description, bid = \
            db.hmget(KEY_BUILD % build_id, build_keys)
        session_id = build_id + '-0'
        state, result = db.hmget(KEY_SESSION % session_id, session_keys)

        history.append(dict(number = number, created = created,
                            description = description,
                            build_id = bid or None,
                            state = state, result = result))
    history.reverse()

    params = merge_job_parameters(repo, results['settings'])
    # Add recipe metadata to build a parameter list
    return jsonify(history = history, parameters = params, **results)


@app.route('/', methods=['GET'])
def list_jobs():
    repo = config()
    jobs = []
    for name in repo.refs.keys():
        if not name.startswith('refs/heads/jobs/'):
            continue
        job_name = name[16:]
        job, job_ref = get_job(repo, job_name, repo.refs[name])
        info = dict(id = job_name,
                    recipe = job['recipe'],
                    description = job.get('description', ''),
                    tags = job.get('tags', []))
        jobs.append(info)
    return jsonify(jobs = jobs)
