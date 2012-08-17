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
RESULT_ERROR = 'error'
RESULT_ABORTED = 'aborted'

BUILD_HISTORY_LIMIT = 100


class Build(object):

    def __init__(self, build_uuid, **kwargs):
        self._uuid        = build_uuid
        self.job_name     = kwargs['job_name']
        self.job_ref      = kwargs['job_ref']
        self.recipe       = kwargs['recipe']
        self.recipe_ref   = kwargs['recipe_ref']
        self.number       = kwargs.get('number', 0)
        self.build_id     = kwargs.get('build_id', '')
        self.description  = kwargs.get('description', '')
        self.created      = kwargs.get('created', get_ts())
        self.next_sess_id = kwargs.get('next_sess_id', 0)
        self.ss_token     = kwargs.get('ss_token', 'SS' + build_uuid)
        self.parameters   = kwargs.get('parameters', {})
        self.artifacts    = kwargs.get('artifacts', [])
        self.state        = kwargs.get('state', SESSION_STATE_NEW)
        self.result       = kwargs.get('result', RESULT_UNKNOWN)

    def as_dict(self):
        return dict(job_name = self.job_name,
                    job_ref = self.job_ref,
                    recipe = self.recipe,
                    recipe_ref = self.recipe_ref,
                    number = self.number,
                    build_id = self.build_id,
                    description = self.description,
                    created = self.created,
                    next_sess_id = self.next_sess_id,
                    ss_token = self.ss_token,
                    parameters = self.parameters,
                    artifacts = self.artifacts,
                    state = self.state,
                    result = self.result)

    def save(self):
        build = self.as_dict()
        build['parameters'] = json.dumps(self.parameters)
        build['artifacts'] = json.dumps(self.artifacts)
        g.db.hmset(KEY_BUILD % self.uuid, build)

    @classmethod
    def set_description(self, build_uuid, description, pipe = None):
        if not pipe:
            pipe = g.db
        pipe.hset(KEY_BUILD % build_uuid, 'description', description)

    @classmethod
    def set_build_id(self, build_uuid, build_id, pipe = None):
        if not pipe:
            pipe = g.db
        pipe.hset(KEY_BUILD % build_uuid, 'build_id', build_id)

    @classmethod
    def set_done(cls, build_uuid, result, pipe):
        pipe.hmset(KEY_BUILD % build_uuid, {'result': result})
        # TODO: Clean the sessions, builds and such?
        # Add to build history
        pipe.lpush(BUILD_HISTORY, build_uuid)
        pipe.ltrim(BUILD_HISTORY, 0, BUILD_HISTORY_LIMIT - 1)

    @classmethod
    def set_state(cls, build_uuid, state, pipe):
        pipe.hmset(KEY_BUILD % build_uuid, {'state': state})

    @classmethod
    def get_job_name(self, build_uuid):
        return g.db.hget(KEY_BUILD % build_uuid, 'job_name')

    @property
    def uuid(self):
        return self._uuid

    @classmethod
    def create(cls, job, parameters = {}, description = ''):
        recipe_ref = job.recipe_ref
        if not recipe_ref:
            recipe_ref = Recipe.load(job.recipe).ref

        build_uuid = 'B%s' % random_sha1()

        build = Build(build_uuid,
                      job_name = job.name, job_ref = job.ref,
                      recipe = job.recipe, recipe_ref = recipe_ref)
        build.save()
        # Create the main session
        create_session(g.db, build.uuid)

        number = g.db.rpush(KEY_JOB_BUILDS % job.name, build.uuid)
        build.number = number
        build.build_id = '%s-%d' % (job.name, number)
        g.db.hmset(KEY_BUILD % build.uuid, {'number': build.number,
                                            'build_id': build.build_id})
        return build

    @classmethod
    def add_artifact(cls, build_uuid, entry):
        key = KEY_BUILD % build_uuid

        def update(pipe):
            files = json.loads(pipe.hget(key, 'artifacts'))
            files.append(entry)
            pipe.multi()
            pipe.hset(key, 'artifacts', json.dumps(files))

        g.db.transaction(update, key)

    @classmethod
    def load(cls, build_uuid):
        build = g.db.hgetall(KEY_BUILD % build_uuid)
        if not build:
            return None
        build['number'] = int(build['number'])
        build['parameters'] = json.loads(build['parameters'])
        build['artifacts'] = json.loads(build['artifacts'])
        return Build(build_uuid, **build)


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


def set_session_state(pipe, session_id, state):
    build_id, num = session_id.split('-')
    if int(num) == 0:
        Build.set_state(build_id, state, pipe=pipe)
    pipe.hset(KEY_SESSION % session_id, 'state', state)


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


def set_session_done(pipe, session_id, result, output, log_file):
    set_session_state(pipe, session_id, SESSION_STATE_DONE)
    pipe.hmset(KEY_SESSION % session_id, {'result': result,
                                          'output': json.dumps(output),
                                          'log_file': log_file,
                                          'ended': get_ts()})


def set_session_queued(pipe, session_id):
    set_session_state(pipe, session_id, SESSION_STATE_QUEUED)


def set_session_to_agent(pipe, session_id, agent_id):
    set_session_state(pipe, session_id, SESSION_STATE_TO_AGENT)
    pipe.hmset(KEY_SESSION % session_id, {'agent': agent_id})


def set_session_running(pipe, session_id):
    set_session_state(pipe, session_id, SESSION_STATE_RUNNING)
    pipe.hmset(KEY_SESSION % session_id, {'started': get_ts()})


def get_session_labels(db, session_id):
    labels = set(db.hget(KEY_SESSION % session_id, 'labels').split(','))
    labels.remove('')
    return labels
