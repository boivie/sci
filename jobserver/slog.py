import json
import types

from sci.slog import JobBegun, JobDone, JobErrorThrown, SetDescription
from jobserver.build import KEY_BUILD
from jobserver.job import KEY_JOB
from jobserver.build import get_session_build

KEY_SLOG = 'slog:%s'

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


def add_slog(db, session_id, item):
    if not type(item) in types.StringTypes:
        item = item.serialize()

    build_id = get_session_build(db, session_id)
    if not build_id:
        return

    db.rpush(KEY_SLOG % session_id, item)
    li = json.loads(item)
    try:
        handler = SLOG_HANDLERS[li['type']]
    except KeyError:
        pass
    else:
        handler(db, build_id, session_id, li)
