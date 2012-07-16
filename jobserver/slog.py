import json
import time
import types

from jobserver.build import Build
from jobserver.job import Job

KEY_SLOG = 'slog:%s'

# TODO: Update sessions when and how?


def DoJobDone(db, build_uuid, session_no, li):
    job_name = Build.get_job_name(build_uuid)
    Job.set_last_success(job_name, build_uuid)


def DoSetDescription(db, build_uuid, session_no, li):
    Build.set_description(build_uuid, li['params']['description'], pipe = db)


def DoSetBuildId(db, build_uuid, session_no, li):
    Build.set_build_id(build_uuid, li['params']['build_id'], pipe = db)


def DoArtifactAdded(db, build_uuid, session_no, li):
    Build.add_artifact(build_uuid, li['params'])


SLOG_HANDLERS = {'job-done': DoJobDone,
                 'set-description': DoSetDescription,
                 'artifact-added': DoArtifactAdded,
                 'set-build-id': DoSetBuildId}


def add_slog(db, session_id, item):
    build_uuid, session_no = session_id.split('-')
    if not type(item) in types.StringTypes:
        item = item.serialize()

    li = json.loads(item)
    li['s'] = int(session_no)
    li['t'] = int(time.time() * 1000)
    db.rpush(KEY_SLOG % build_uuid, json.dumps(li))
    try:
        handler = SLOG_HANDLERS[li['type']]
    except KeyError:
        pass
    else:
        handler(db, build_uuid, session_no, li)
