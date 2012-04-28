import logging, time

import redis

from sci.utils import random_sha1
from jobserver.build import get_session
from jobserver.build import set_session_queued
import jobserver.db as jdb
from .dispatch import do_dispatch

SEEN_EXPIRY_TTL = 2 * 60


class DispatchSession(object):
    queue = 'queue'

    @staticmethod
    def allocate(pipe, agent_id, session_id):
        """Starts multi, doesn't exec"""
        # The agent may become inactive
        pipe.watch(jdb.KEY_AGENT % agent_id)
        info = pipe.hgetall(jdb.KEY_AGENT % agent_id)
        info['seen'] = int(info['seen'])

        pipe.multi()
        pipe.srem(jdb.KEY_AVAILABLE, agent_id)
        if info['state'] != jdb.AGENT_STATE_AVAIL:
            return None

        # verify the 'seen' so that it's not too old
        if info['seen'] + SEEN_EXPIRY_TTL < int(time.time()):
            pipe.hset(jdb.KEY_AGENT % agent_id, 'state', jdb.AGENT_STATE_INACTIVE)
            return None

        pipe.hmset(jdb.KEY_AGENT % agent_id, {'state': jdb.AGENT_STATE_PENDING,
                                              'session': session_id})
        return info

    @staticmethod
    def perform(session_id):
        db = jdb.conn()
        session = get_session(db, session_id)
        lkeys = [jdb.KEY_LABEL % label for label in session['labels']]
        lkeys.append(jdb.KEY_AVAILABLE)
        ts = float(time.time() * 1000)
        alloc_key = jdb.KEY_ALLOCATION % random_sha1()

        while True:
            with db.pipeline() as pipe:
                try:
                    pipe.watch(jdb.KEY_AVAILABLE)
                    pipe.sinterstore(alloc_key, lkeys)
                    agent_id = pipe.spop(alloc_key)
                    if not agent_id:
                        pipe.multi()
                        set_session_queued(pipe, session_id)
                        pipe.zadd(jdb.KEY_QUEUED_SESSIONS, ts, session_id)
                        pipe.delete(alloc_key)
                        pipe.execute()
                        logging.debug("No agent available - queuing")
                    else:
                        agent_info = DispatchSession.allocate(pipe,
                                                              agent_id,
                                                              session_id)
                        pipe.delete(alloc_key)
                        pipe.execute()

                        if not agent_info:
                            logging.debug("Tried to allocate %s. Bummer" % agent_id)
                            continue

                        logging.debug("Dispatching to %s" % agent_id)
                        do_dispatch(db, agent_id, agent_info, session_id)
                    return
                except redis.WatchError:
                    continue
