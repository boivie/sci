import json

from flask import g

from sci.utils import random_sha1
from jobserver.utils import get_ts
from jobserver.recipe import Recipe
from jobserver.db import BUILD_HISTORY

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

BUILD_HISTORY_LIMIT = 100


def new_build(job, parameters = {}, description = ''):
    recipe_ref = job.recipe_ref
    if not recipe_ref:
        recipe_ref = Recipe.load(job.recipe).ref

    # Insert the build (first without build number, as we don't know it)
    build_id = 'B%s' % random_sha1()
    # The 'state' and 'result' are the same as session-0's, but we keep them
    # here to be able to do smarter queries.
    build = dict(job_name = job.name,
                 job_ref = job.ref,
                 recipe = job.recipe,
                 recipe_ref = recipe_ref,
                 number = 0,
                 build_id = '',
                 description = description,
                 created = get_ts(),
                 next_sess_id = 0,  # will be incremented to 1 below
                 ss_token = get_ss_token(build_id),
                 parameters = json.dumps(parameters),
                 artifacts = json.dumps([]),
                 state = SESSION_STATE_NEW,
                 result = RESULT_UNKNOWN)
    g.db.hmset(KEY_BUILD % build_id, build)

    # Create the main session
    create_session(g.db, build_id)

    number = g.db.rpush(KEY_JOB_BUILDS % job.name, build_id)
    values = {'number': number,
              'build_id': '%s-%d' % (job.name, number)}
    build['number'] = values['number']
    build['build_id'] = values['build_id']
    build['uuid'] = build_id
    g.db.hmset(KEY_BUILD % build_id, values)
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
    build['artifacts'] = json.loads(build['artifacts'])
    return build


def create_session(db, build_id, parent = None, labels = [],
                   run_info = None, state = SESSION_STATE_NEW):
    ri = run_info or {}
    args = ", ".join(ri.get('args', []))
    title = "%s(%s)" % (ri.get('step_name', 'main'), args)

    session = dict(state = state,
                   title = title,
                   result = RESULT_UNKNOWN,
                   parent = parent,
                   labels = ",".join(labels),
                   agent = '',
                   run_info = json.dumps(run_info),
                   log_file = '',
                   created = get_ts(),
                   started = 0,
                   ended = 0,
                   output = json.dumps(None))
    session_no = db.hincrby(KEY_BUILD % build_id, 'next_sess_id', 1) - 1
    session_id = '%s-%s' % (build_id, session_no)
    db.hmset(KEY_SESSION % session_id, session)
    return session_no


def get_session_title(session):
    return session.get('title', '')


def get_session(db, session_id):
    session = db.hgetall(KEY_SESSION % session_id)
    if not session:
        return None
    session['labels'] = set(session['labels'].split(','))
    session['labels'].remove('')  # if labels is empty
    session['run_info'] = json.loads(session.get('run_info', '{}'))
    session['output'] = json.loads(session['output'])
    session['created'] = int(session.get('created', '0'))
    session['started'] = int(session.get('started', '0'))
    session['ended'] = int(session.get('ended', '0'))
    return session


def set_build_done(pipe, build_id, result):
    pipe.hmset(KEY_BUILD % build_id, {'state': SESSION_STATE_DONE,
                                      'result': result})
    # TODO: Clean the sessions, builds and such?
    # Add to build history
    pipe.lpush(BUILD_HISTORY, build_id)
    pipe.ltrim(BUILD_HISTORY, 0, BUILD_HISTORY_LIMIT - 1)


def set_session_done(pipe, session_id, result, output, log_file):
    pipe.hmset(KEY_SESSION % session_id, {'state': SESSION_STATE_DONE,
                                          'result': result,
                                          'output': json.dumps(output),
                                          'log_file': log_file,
                                          'ended': get_ts()})


def set_session_queued(pipe, session_id):
    pipe.hmset(KEY_SESSION % session_id, {'state': SESSION_STATE_QUEUED})


def set_session_to_agent(pipe, session_id, agent_id):
    pipe.hmset(KEY_SESSION % session_id, {'state': SESSION_STATE_TO_AGENT,
                                          'agent': agent_id})


def set_session_running(pipe, session_id):
    pipe.hmset(KEY_SESSION % session_id, {'state': SESSION_STATE_RUNNING,
                                          'started': get_ts()})


def get_session_labels(db, session_id):
    labels = set(db.hget(KEY_SESSION % session_id, 'labels').split(','))
    labels.remove('')
    return labels
