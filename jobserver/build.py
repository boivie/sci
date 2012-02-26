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
STATE_NEW = 'new'
STATE_QUEUED = 'queued'
# The session has been dispatched to a agent, but it has not yet ack'ed.
STATE_DISPATCHED = 'dispatched'
STATE_RUNNING = 'running'
# The agent has finished (successfully, or with errors) - see RESULT_
STATE_DONE = 'done'

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
    session_id = create_session(db, build_id)
    build = dict(job_name = job['name'],
                 job_ref = job_ref,
                 recipe_name = job['recipe_name'],
                 recipe_ref = recipe_ref,
                 number = 0,
                 description = '',
                 created = now,
                 session_id = session_id,
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


def create_session(db, build_id, input = None, state = STATE_NEW):
    session_id = 'S' + random_sha1()
    session = dict(build_id = build_id,
                   created = get_ts(),
                   state = state,
                   result = RESULT_UNKNOWN,
                   input = json.dumps(input),
                   agent = None,
                   output = json.dumps(None))
    db.hmset(KEY_SESSION % session_id, session)
    db.sadd(KEY_BUILD_SESSIONS % build_id, session_id)
    return session_id


def get_session(db, session_id):
    session = db.hgetall(KEY_SESSION % session_id)
    session['input'] = json.loads(session['input'])
    session['output'] = json.loads(session['output'])
    return session


def set_session_done(db, session_id, result, output):
    db.hmset(KEY_SESSION % session_id, {'state': STATE_DONE,
                                        'result': result,
                                        'output': json.dumps(output)})


def set_session_queued(db, session_id):
    db.hmset(KEY_SESSION % session_id, {'state': STATE_QUEUED})


def set_session_dispatched(db, session_id, agent_id):
    db.hmset(KEY_SESSION % session_id, {'state': STATE_DISPATCHED,
                                        'agent': agent_id})


def get_build_sessions(db, build_id):
    return db.smembers(KEY_BUILD_SESSIONS % build_id)


def get_session_build(db, session_id):
    return db.hget(KEY_SESSION % session_id, 'build_id')
