from flask import Blueprint, request, jsonify, abort, g

from jobserver.db import KEY_JOBS
from jobserver.build import KEY_JOB_BUILDS
from jobserver.job import Job, JobNotFound, JobNotCurrent
from jobserver.utils import chunks

app = Blueprint('job', __name__)


@app.route('/<name>/create', methods=['POST'])
def create_job(name):
    job = Job.parse(name, "recipe: %s" % request.json.get('recipe'))
    try:
        job.save()
    except JobNotCurrent:
        print("Job already exists!")
        abort(412)
    return jsonify(ref = job.ref)


@app.route('/<name>/raw', methods=['POST'])
def put_job_raw(name):
    raw = request.json['yaml']
    job = Job.parse(name, raw)
    try:
        job.save(prev_ref = request.json.get('old'))
    except JobNotCurrent:
        abort(412)
    return jsonify(ref = job.ref)


@app.route('/<name>', methods=['GET'])
def get_job(name):
    try:
        job = Job.load(name, ref = request.args.get('ref'))
    except JobNotFound:
        abort(404)
    blen = job.latest_build

    history = []
    if request.args.get('history'):
        fields = ('#', 'build:*->number', 'build:*->created',
                  'build:*->description', 'build:*->build_id',
                  'build:*->state', 'build:*->result')
        for d in chunks(g.db.sort(KEY_JOB_BUILDS % name, start = blen - 10,
                                  num = 10, by='nosort', get=fields), 7):
            history.append(dict(number = int(d[1]), created = d[2],
                                description = d[3],
                                build_id = d[4] or None,
                                state = d[5], result = d[6]))
        history.reverse()

    yaml_str = job.yaml if request.args.get('yaml') else None

    return jsonify(name = job.name,
                   ref = job.ref,
                   recipe = job.recipe,
                   recipe_ref = job.recipe_ref,
                   description = job.description,
                   tags = job.tags,
                   success_no = job.last_success,
                   latest_no = blen,
                   history = history,
                   parameters = job.parameters,
                   merged_params = job.get_merged_params(),
                   yaml = yaml_str)


@app.route('/', methods=['GET'])
def list_jobs():
    fields = ('#', 'job:*->tags', 'job:*->description')
    jobs = [{'id': d[0], 'description': d[2],
             'tags': [t for t in d[1].split(',') if t]}
            for d in chunks(g.db.sort(KEY_JOBS, get=fields), 3)]
    return jsonify(jobs = jobs)
