"""
    sci.node
    ~~~~~~~~

    Handle nodes

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
import sys, subprocess, json


class Node(object):
    """Represents a node"""
    def __init__(self, node_id, server_url, node_key):
        self.node_id = node_id
        self.server_url = server_url
        self.node_key = node_key

    def _serialize(self, job, fun, args, kwargs):
        return {"node_id": self.node_id,
                "funname": fun.__name__,
                "jobfname": sys.modules[job.import_name].__file__,
                "args": args,
                "kwargs": kwargs,
                "env": dict(job.env),
                "params": dict(job.params),
                "config": dict(job.config)}

    def run(self, job, fun, args, kwargs):
        """Runs a job on this node."""
        data = self._serialize(job, fun, args, kwargs)
        args = ["./run_job.py"]
        proc = subprocess.Popen(args, stdin = subprocess.PIPE)
        proc.stdin.write(json.dumps(data))
        proc.stdin.close()
        return proc
