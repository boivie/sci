import json

from sci.utils import random_sha1
from jobserver.utils import get_ts
from jobserver.gitdb import config
from jobserver.recipe import get_recipe_ref

KEY_JOB_BUILDS = 'job:builds:%s'
KEY_BUILD = 'build:%s'
KEY_BUILD_SESSIONS = 'sessions:%s'

KEY_SESSION = 'session:%s'

# The session is created, but not yet scheduled to run
BUILD_STATE_NEW = 'new'
BUILD_STATE_QUEUED = 'queued'
# The session has been dispatched to a agent, but it has not yet ack'ed.
BUILD_STATE_DISPATCHED = 'dispatched'
BUILD_STATE_RUNNING = 'running'
# The agent has finished (successfully, or with errors) - see RESULT_
BUILD_STATE_DONE = 'done'

RESULT_UNKNOWN = 'unknown'
RESULT_SUCCESS = 'success'
RESULT_FAILED = 'failed'
RESULT_ABORTED = 'aborted'


def new_build(db, job, job_ref, parameters = {}):
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
                 description = '',
                 created = now,
                 max_session = 0,
                 parameters = json.dumps(parameters))
    db.hmset(KEY_BUILD % build_id, build)

    create_session(db, build_id)
    build['session_id'] = build_id + '-1'

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


def create_session(db, build_id, input = None, state = BUILD_STATE_NEW):
    session = dict(created = get_ts(),
                   state = state,
                   result = RESULT_UNKNOWN,
                   input = json.dumps(input),
                   agent = None,
                   output = json.dumps(None))
    session_no = db.hincrby(KEY_BUILD % build_id, 'max_session', 1)
    session_id = '%s-%s' % (build_id, session_no)
    db.hmset(KEY_SESSION % session_id, session)
    return session_no


def get_session(db, session_id):
    session = db.hgetall(KEY_SESSION % session_id)
    if not session:
        return None
    session['input'] = json.loads(session['input'])
    session['output'] = json.loads(session['output'])
    return session


def set_session_done(db, session_id, result, output):
    db.hmset(KEY_SESSION % session_id, {'state': BUILD_STATE_DONE,
                                        'result': result,
                                        'output': json.dumps(output)})


def set_session_queued(db, session_id):
    db.hmset(KEY_SESSION % session_id, {'state': BUILD_STATE_QUEUED})


def set_session_dispatched(db, session_id, agent_id):
    db.hmset(KEY_SESSION % session_id, {'state': BUILD_STATE_DISPATCHED,
                                        'agent': agent_id})


def set_session_running(db, session_id):
    db.hmset(KEY_SESSION % session_id, {'state': BUILD_STATE_RUNNING})
