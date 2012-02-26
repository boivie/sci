import json

from sci.utils import random_sha1
from jobserver.utils import get_ts
from jobserver.gitdb import config
from jobserver.recipe import get_recipe_ref

KEY_JOB_BUILDS = 'job:builds:%s'
KEY_BUILD = 'build:%s'

STATE_PREPARED = 'prepared'
STATE_QUEUED = 'queued'
STATE_DISPATCHED = 'dispatched'
STATE_RUNNING = 'running'
STATE_DONE = 'done'
STATE_FAILED = 'failed'
STATE_ABORTED = 'aborted'


def new_build(db, job, job_ref, parameters = {},
              state = STATE_PREPARED):
    repo = config()
    recipe_ref = job.get('recipe_ref')
    if not recipe_ref:
        recipe_ref = get_recipe_ref(repo, job['recipe_name'])

    now = get_ts()

    # Insert the build (first without build number, as we don't know it)
    build_id = 'B%s' % random_sha1()
    build = dict(job_name = job['name'],
                 job_ref = job_ref,
                 recipe_name = job['recipe_name'],
                 recipe_ref = recipe_ref,
                 number = 0,
                 state = state,
                 description = '',
                 created = now,
                 session_id = 'S%s' % random_sha1(),
                 parameters = json.dumps(parameters))
    db.hmset(KEY_BUILD % build_id, build)

    number = db.rpush(KEY_JOB_BUILDS % job['name'], build_id)
    db.hset(KEY_BUILD % build_id, 'number', number)
    return build_id, build


def get_build_info(db, build_id):
    build = db.hgetall(KEY_BUILD % build_id)
    if not build:
        return None
    build['number'] = int(build['number'])
    build['parameters'] = json.loads(build['parameters'])
    return build
