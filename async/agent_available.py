import logging
import jobserver.db as jdb
from jobserver.build import get_session_labels
from .dispatch import do_dispatch


class AgentAvailable(object):
    queue = 'queue'

    @staticmethod
    def perform(agent_id):
        db = jdb.conn()
        matched = None
        agent_labels = set(db.hget(jdb.KEY_AGENT % agent_id, 'labels').split(','))
        queued = db.zrange(jdb.KEY_QUEUED_SESSIONS, 0, -1)
        if queued:
            logging.info("Agent %s available - matching against "
                         "%d queued sessions" % (agent_id, len(queued)))
            for session_id in queued:
                labels = get_session_labels(db, session_id)
                if labels.issubset(agent_labels):
                    matched = session_id
                    break
            db.zrem(jdb.KEY_QUEUED_SESSIONS, matched)
            logging.debug("Matched against %s" % matched)
        else:
            logging.info("Agent %s available - nothing queued." % agent_id)

        if matched:
            agent_info = db.hgetall(jdb.KEY_AGENT % agent_id)
            do_dispatch(db, agent_id, agent_info, matched)
        else:
            db.sadd(jdb.KEY_AVAILABLE, agent_id)
