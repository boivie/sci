import json
KEY_QUEUE = 'js:queue'


class QueueItem(object):
    def __init__(self):
        self.params = {}

    def serialize(self):
        d = dict(type = self.type)
        if self.params:
            d['params'] = self.params
        return json.dumps(d)


class DispatchSession(QueueItem):
    type = 'dispatch-sess'

    def __init__(self, session_id):
        self.params = dict(session_id = session_id)


class AgentAvailable(QueueItem):
    type = 'agent-avail'

    def __init__(self, agent_id):
        self.params = dict(agent_id = agent_id)


class UpdateArtifacts(QueueItem):
    type = 'update-artifacts'

    def __init__(self, build_id):
        self.params = dict(build_id = build_id)


def queue(db, item, front = False):
    if front:
        db.lpush(KEY_QUEUE, item.serialize())
    else:
        db.rpush(KEY_QUEUE, item.serialize())
