import json


class QueueItem(object):
    def __init__(self):
        self.params = {}

    def serialize(self):
        d = dict(type = self.type)
        if self.params:
            d['params'] = self.params
        return json.dumps(d)


class StartBuildQ(QueueItem):
    type = 'start-build'

    def __init__(self, build_id, session_id):
        self.params = dict(build_id = build_id,
                           session_id = session_id)
