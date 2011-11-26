"""
    sci.agents
    ~~~~~~~~~~

    Agents

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
import json
from .http_client import HttpClient
from .node import Node

STATE_NONE, STATE_QUEUED, STATE_PREPARED, STATE_RUNNING, STATE_DONE = range(5)


class Agent(object):
    def __init__(self, step, args, kwargs):
        self.step = step
        self.args = args
        self.kwargs = kwargs
        self.state = STATE_NONE

    def run(self, ahq_url, job):
        data = Node._serialize(job, self.step.fun, self.args, self.kwargs)
        data = json.dumps(dict(labels = ['any'],
                               data = json.dumps(data)))
        res = HttpClient(ahq_url).call('/J%s/dispatch.json' % job.build_id,
                                       input = data)
        self.dispatch_id = res['id']
        self.state = STATE_RUNNING

    def join(self, url):
        assert(self.state == STATE_RUNNING)
        res = HttpClient(url).call('/%s/result.json' % self.dispatch_id)
        self.result = res['result']
        self.state = STATE_DONE


class Agents(object):
    def __init__(self, job, url):
        self.agents = []
        self.job = job
        self._ahq_url = url

    def async(self, step, args = [], kwargs = {}):
        agent = Agent(step, args, kwargs)
        agent.state = STATE_PREPARED
        self.agents.append(agent)
        return agent

    def run(self):
        for agent in self.agents:
            agent.run(self._ahq_url, self.job)

        for agent in self.agents:
            agent.join(self._ahq_url)

        # Return all the return values
        res = [a.result for a in self.agents]

        self.agents = []
        return res
