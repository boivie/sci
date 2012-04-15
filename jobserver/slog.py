import json
import time
import types

from sci.slog import JobDone, SetDescription, ArtifactAdded, SetBuildId
from jobserver.build import KEY_BUILD, add_build_artifact
from jobserver.job import KEY_JOB

KEY_SLOG = 'slog:%s'

# TODO: Update sessions when and how?


def DoJobDone(db, build_id, session_no, li):
    # Set the job's last success to this one
    job = db.hget(KEY_BUILD % build_id, 'job_name')
    if job:
        db.hset(KEY_JOB % job, 'success', build_id)


def DoSetDescription(db, build_id, session_no, li):
    db.hset(KEY_BUILD % build_id, 'description', li['params']['description'])


def DoSetBuildId(db, build_id, session_no, li):
    db.hset(KEY_BUILD % build_id, 'build_id', li['params']['build_id'])


def DoArtifactAdded(db, build_id, session_no, li):
    add_build_artifact(db, build_id, li['params'])


SLOG_HANDLERS = {JobDone.type: DoJobDone,
                 SetDescription.type: DoSetDescription,
                 ArtifactAdded.type: DoArtifactAdded,
                 SetBuildId.type: DoSetBuildId}


def add_slog(db, session_id, item):
    build_id, session_no = session_id.split('-')
    if not type(item) in types.StringTypes:
        item = item.serialize()

    li = json.loads(item)
    li['s'] = int(session_no)
    li['t'] = int(time.time() * 1000)
    db.rpush(KEY_SLOG % build_id, json.dumps(li))
    try:
        handler = SLOG_HANDLERS[li['type']]
    except KeyError:
        pass
    else:
        handler(db, build_id, session_no, li)
