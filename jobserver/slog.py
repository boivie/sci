import json

from sci.slog import JobBegun, JobDone, JobErrorThrown, SetDescription
from jobserver.build import KEY_BUILD
from jobserver.job import KEY_JOB

KEY_SLOG = 'slog:%s:%s'

# TODO: Update sessions when and how?


def DoJobDone(db, build_id, session_id, li):
    # Set the job's last success to this one
    job = db.hget(KEY_BUILD % build_id, 'job_name')
    if job:
        db.hset(KEY_JOB % job, 'success', build_id)


def DoJobErrorThrown(db, build_id, session_id, li):
    pass


def DoJobBegun(db, build_id, session_id, li):
    pass


def DoSetDescription(db, build_id, session_id, li):
    db.hset(KEY_BUILD % build_id, 'description', li['params']['description'])


SLOG_HANDLERS = {JobBegun.type: DoJobBegun,
                 JobDone.type: DoJobDone,
                 JobErrorThrown.type: DoJobErrorThrown,
                 SetDescription.type: DoSetDescription}


def add_slog(db, build_id, session_id, data):
    db.rpush(KEY_SLOG % (build_id, session_id), data)
    li = json.loads(data)
    try:
        handler = SLOG_HANDLERS[li['type']]
    except KeyError:
        pass
    else:
        handler(db, build_id, session_id, li)
