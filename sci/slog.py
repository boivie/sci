"""
    sci.slog
    ~~~~~~~~

    SCI Streaming Log

    A build will stream structured log data to the job server.

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
import json


class LogItem(object):
    def __init__(self):
        self.params = {}

    def serialize(self):
        d = dict(type = self.type)
        if self.params:
            d['params'] = self.params
        return json.dumps(d)


class StepBegun(LogItem):
    type = 'step-begun'

    def __init__(self, name, args, kwargs):
        self.params = dict(name = name, args = args, kwargs = kwargs)


class StepFunDone(LogItem):
    type = 'step-fun-done'

    def __init__(self, name, time):
        self.params = dict(name = name, time = int(time))


class StepJoined(LogItem):
    type = 'step-joined'

    def __init__(self, name, time):
        self.params = dict(name = name, time = int(time))


class JobBegun(LogItem):
    type = 'job-begun'


class JobDone(LogItem):
    type = 'job-done'


class JobErrorThrown(LogItem):
    type = 'job-error'

    def __init__(self, what):
        self.params = dict(what = what)


class SetDescription(LogItem):
    type = 'set-description'

    def __init__(self, description):
        self.params = dict(description = description)


class SessionStarted(LogItem):
    type = 'session-start'


class SessionDone(LogItem):
    type = 'session-done'

    def __init__(self, result):
        self.params = dict(result = result)


class QueuedSession(LogItem):
    type = 'queued-session'

    def __init__(self, session_id):
        self.params = dict(session_id = session_id)
