"""
    sci.agents
    ~~~~~~~~~~

    Agents

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
import json
import time
from .http_client import HttpClient
from sci.slog import AsyncJoined
STATE_NONE, STATE_PREPARED, STATE_RUNNING, STATE_DONE = range(4)


class Agent(object):
    def __init__(self, step, args, kwargs):
        self.step = step
        self.args = args
        self.kwargs = kwargs
        self.state = STATE_NONE

    def run(self, url, job):
        data = {"build_id": job.build_id,
                "job_server": job.jobserver,
                "funname": self.step.fun.__name__,
                "step_name": self.step.name,
                "args": self.args,
                "kwargs": self.kwargs,
                "env": job.env.serialize(),
                "labels": ['any'],
                "parent_session": job.session.id}
        self.ts_start = time.time()
        res = HttpClient(url).call('/agent/dispatch', input = json.dumps(data))
        self.session_id = res['session_id']
        self.state = STATE_RUNNING

    def join(self, url, job):
        assert(self.state == STATE_RUNNING)
        res = HttpClient(url).call('/agent/result/%s' % self.session_id)
        self.output = res['output']
        self.result = res['result']
        self.state = STATE_DONE
        session_no = self.session_id.split('-')[-1]
        diff = (time.time() - self.ts_start) * 1000
        job.slog(AsyncJoined(session_no, diff))


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
            agent.join(self._ahq_url, self.job)

        # Return all the return values
        res = [a.output for a in self.agents]

        self.agents = []
        return res

    def should_run(self):
        for agent in self.agents:
            if agent.state != STATE_DONE:
                return True
        return False
