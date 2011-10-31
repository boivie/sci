"""
    sci.node
    ~~~~~~~~

    Handle nodes

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
import sys, imp
import cPickle as pickle
from multiprocessing import Process


class Node(object):
    """Represents a node"""
    def __init__(self, node_id, server_url, node_key):
        self.node_id = node_id
        self.server_url = server_url
        self.node_key = node_key

    def _serialize(self, job, fun, args, kwargs):
        data = {"node_id": self.node_id,
                "funname": fun.__name__,
                "jobfname": sys.modules[job.import_name].__file__,
                "args": args,
                "kwargs": kwargs,
                "env": dict(job.env),
                "params": dict(job.params),
                "config": dict(job.config)}
        return pickle.dumps(data, 2)

    def _run_job(self, data):
        data = pickle.loads(data)
        print(data["node_id"] + ": running on remote node")
        d = imp.new_module('config')
        d.__file__ = data["jobfname"]
        execfile(data["jobfname"], d.__dict__)
        # Find the 'job' variable
        from .job import Job
        for k in dir(d):
            var = getattr(d, k)
            if issubclass(var.__class__, Job):
                var.start_subjob(data["funname"], data["args"],
                                 data["kwargs"],
                                 data["env"], data["params"], data["config"],
                                 data["node_id"])

    def run(self, job, fun, args, kwargs):
        """Runs a job on this node."""
        data = self._serialize(job, fun, args, kwargs)
        p = Process(target = self._run_job, args = (data,))
        p.start()
        return p
