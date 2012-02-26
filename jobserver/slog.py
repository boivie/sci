import json

from sci.slog import JobBegun, JobDone, JobErrorThrown, SetDescription
from jobserver.build import KEY_BUILD, STATE_DONE, STATE_FAILED, STATE_RUNNING
from jobserver.job import KEY_JOB

KEY_BUILD_SESSIONS = 'build-sessions:%s'
KEY_SLOG = 'slog:%s:%s'


def DoJobDone(db, build_id, li):
    db.hset(KEY_BUILD % build_id, 'state', STATE_DONE)
    # Set the job's last success to this one
    job = db.hget(KEY_BUILD % build_id, 'job_name')
    if job:
        db.hset(KEY_JOB % job, 'success', build_id)


def DoJobErrorThrown(db, build_id, li):
    db.hset(KEY_BUILD % build_id, 'state', STATE_FAILED)


def DoJobBegun(db, build_id, li):
    db.hset(KEY_BUILD % build_id, 'state', STATE_RUNNING)


def DoSetDescription(db, build_id, li):
    db.hset(KEY_BUILD % build_id, 'description', li['params']['description'])


SLOG_HANDLERS = {JobBegun.type: DoJobBegun,
                 JobDone.type: DoJobDone,
                 JobErrorThrown.type: DoJobErrorThrown,
                 SetDescription.type: DoSetDescription}


def add_slog(db, build_id, session_id, data):
    # Verify that the build id exists.
    if not db.exists(KEY_BUILD % build_id):
        return False
    db.sadd(KEY_BUILD_SESSIONS % build_id, session_id)
    db.rpush(KEY_SLOG % (build_id, session_id), data)
    li = json.loads(data)
    try:
        handler = SLOG_HANDLERS[li['type']]
    except KeyError:
        pass
    else:
        handler(db, build_id, li)
    return True
