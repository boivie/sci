"""
    sci.agents
    ~~~~~~~~~~

    Agents

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
import logging, json
from .node import LocalNode, RemoteNode
from .http_client import HttpClient


STATE_NONE, STATE_QUEUED, STATE_PREPARED, STATE_RUNNING, STATE_DONE = range(5)


class Agent(object):
    def __init__(self, step, args, kwargs, node):
        self.node = node
        self.step = step
        self.args = args
        self.kwargs = kwargs
        self.state = STATE_NONE

    def run(self, job):
        self.detached_job = self.node.run(job, self.step.fun,
                                          self.args, self.kwargs)
        self.state = STATE_RUNNING

    def poll(self):
        assert(self.state == STATE_RUNNING)
        if self.detached_job.poll():
            self.state = STATE_DONE
        return self.state == STATE_DONE

    def join(self):
        assert(self.state == STATE_RUNNING)
        self.detached_job.join()
        self.state = STATE_DONE

    def result(self):
        return self.detached_job._return_value


class Agents(object):
    def __init__(self, job, url):
        self.agents = []
        self.job = job
        self._ahq_url = url

    def async(self, step, *args, **kwargs):
        ok, node_or_ticket = Agents._allocate_node(self._ahq_url)
        agent = Agent(step, args, kwargs, node_or_ticket)
        if ok:
            agent.state = STATE_PREPARED
        else:
            agent.state = STATE_QUEUED
        self.agents.append(agent)
        return agent

    @classmethod
    def _allocate_node(cls, url):
        if url is None:
            return True, LocalNode()

        req = {"labels": ["any"]}
        result = HttpClient(url).call("/allocate.json", input = json.dumps(req))
        if result["status"] == "ok":
            logging.debug("Allocated A%s (%s)" % (result["agent"],
                                                  result["url"]))
            return True, RemoteNode(result["url"], result["job_token"])
        elif result["status"] == "queued":
            logging.debug("Queued for allocation: T%s" % result["ticket"])
            return False, result["ticket"]
        else:
            raise Exception("Failed to allocate slave")

    def _running(self):
        return [a for a in self.agents if a.state == STATE_RUNNING]

    def _queued(self):
        return [a for a in self.agents if a.state == STATE_QUEUED]

    def run(self):
        ahq = HttpClient(self._ahq_url)

        # Start agents that haven't been started
        for agent in self.agents:
            if agent.state == STATE_PREPARED:
                agent.run(self.job)

        while True:
            # Hand in tickets, get agents
            queued = self._queued()
            if queued:
                tickets = [a.node for a in queued]
                result = ahq.call("/tickets.json",
                                  input = json.dumps({"tickets": tickets}))
                if result["status"] == "ok":
                    agent = [a for a in self.agents
                             if a.node == result["ticket"]][0]
                    logging.debug("Got A%s from T%s" % (result["agent"],
                                                        result["ticket"][0:7]))
                    agent.node = RemoteNode(result["url"], result["job_token"])
                    agent.run(self.job)

            # If we are just waiting for jobs to continue, block here.
            # otherwise, just check for finished jobs and continue
            if self._queued():
                for agent in self._running():
                    agent.poll()
                continue

            for agent in self._running():
                agent.join()

            # We have joined all agents. We are done.
            break
        # Return all the return values
        return [a.result() for a in self.agents]
