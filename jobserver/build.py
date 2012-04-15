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
SESSION_STATE_NEW = 'new'
# The session is scheduled to be handled by the backend
SESSION_STATE_TO_BACKEND = 'to-backend'
# No agent can processed the session, so it's queued and awaiting an agent
SESSION_STATE_QUEUED = 'queued'
# The session has been dispatched to a agent, but it has not yet ack'ed.
SESSION_STATE_TO_AGENT = 'to-agent'
# The session has been reported to be running
SESSION_STATE_RUNNING = 'running'
# The agent has finished (successfully, or with errors) - see RESULT_
SESSION_STATE_DONE = 'done'

RESULT_UNKNOWN = 'unknown'
RESULT_SUCCESS = 'success'
RESULT_FAILED = 'failed'
RESULT_ABORTED = 'aborted'


def new_build(db, job, job_ref, parameters = {}, description = ''):
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
                 build_id = '',  # this is the external id
                 description = description,
                 created = now,
                 session_id = '%s-1' % build_id,
                 max_session = 0,  # will be incremented to 1 below
                 ss_token = get_ss_token(build_id),
                 parameters = json.dumps(parameters),
                 artifacts = json.dumps([]))
    db.hmset(KEY_BUILD % build_id, build)

    # Create the main session
    create_session(db, build_id)

    number = db.rpush(KEY_JOB_BUILDS % job['name'], build_id)
    values = {'number': number,
              'build_id': '%s-%d' % (job['name'], number)}
    build['number'] = values['number']
    build['build_id'] = values['build_id']
    build['uuid'] = build_id
    db.hmset(KEY_BUILD % build_id, values)
    return build


def get_ss_token(build_id):
    return "SS" + build_id


def add_build_artifact(db, build_id, entry):
    key = KEY_BUILD % build_id

    def update(pipe):
        files = json.loads(db.hget(key, 'artifacts'))
        files.append(entry)
        pipe.multi()
        pipe.hset(key, 'artifacts', json.dumps(files))

    db.transaction(update, key)


def get_build_info(db, build_id):
    build = db.hgetall(KEY_BUILD % build_id)
    if not build:
        return None
    build['number'] = int(build['number'])
    build['parameters'] = json.loads(build['parameters'])
    print(build_id)
    build['artifacts'] = json.loads(build['artifacts'])
    return build


def create_session(db, build_id, parent = None, labels = [],
                   run_info = None, state = SESSION_STATE_NEW):
    session = dict(created = get_ts(),
                   state = state,
                   result = RESULT_UNKNOWN,
                   parent = parent,
                   labels = ",".join(labels),
                   agent = '',
                   run_info = json.dumps(run_info),
                   log_file = '',
                   output = json.dumps(None))
    session_no = db.hincrby(KEY_BUILD % build_id, 'max_session', 1)
    session_id = '%s-%s' % (build_id, session_no)
    db.hmset(KEY_SESSION % session_id, session)
    return session_no


def get_session(db, session_id):
    session = db.hgetall(KEY_SESSION % session_id)
    if not session:
        return None
    session['labels'] = session['labels'].split(',')
    session['labels'].remove('')  # if labels is empty
    session['run_info'] = json.loads(session['run_info'])
    session['output'] = json.loads(session['output'])
    return session


def set_session_done(db, session_id, result, output, log_file):
    db.hmset(KEY_SESSION % session_id, {'state': SESSION_STATE_DONE,
                                        'result': result,
                                        'output': json.dumps(output),
                                        'log_file': log_file})


def set_session_queued(db, session_id):
    db.hmset(KEY_SESSION % session_id, {'state': SESSION_STATE_QUEUED})


def set_session_to_agent(db, session_id, agent_id):
    db.hmset(KEY_SESSION % session_id, {'state': SESSION_STATE_TO_AGENT,
                                        'agent': agent_id})


def set_session_running(db, session_id):
    db.hmset(KEY_SESSION % session_id, {'state': SESSION_STATE_RUNNING})


def get_session_labels(db, session_id):
    labels = set(db.hget(KEY_SESSION % session_id, 'labels').split(','))
    labels.remove('')
    return labels
