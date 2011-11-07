"""
    sci.node
    ~~~~~~~~

    Handle nodes

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
import sys, subprocess, json
from .session import Session


class DetachedJob(object):
    def __init__(self, node_id):
        self.node_id = node_id

    def join(self):
        raise NotImplemented()


class Node(object):
    """Represents a node"""
    def __init__(self, node_id, server_url, node_key):
        self.node_id = node_id

    def _serialize(self, job, fun, args, kwargs):
        return {"node_id": self.node_id,
                "funname": fun.__name__,
                "jobfname": sys.modules[job._import_name].__file__,
                "args": args,
                "kwargs": kwargs,
                "env": dict(job.env),
                "params": dict(job.params),
                "config": dict(job.config)}

    def run_remote(self, data):
        raise NotImplemented()

    def run(self, job, fun, args, kwargs):
        """Runs a job on this node."""
        data = self._serialize(job, fun, args, kwargs)
        return self.run_remote(json.dumps(data))


class LocalDetachedJob(DetachedJob):
    def __init__(self, node_id, proc):
        super(LocalDetachedJob, self).__init__(node_id)
        self.proc = proc

    def join(self):
        self.proc.wait()


class LocalNode(Node):
    def run_remote(self, data):
        # Create a session
        session = Session.create()
        d = json.loads(data)
        d["sid"] = session.id
        args = ["./run_job.py"]
        stdout = open(session.logfile, "w")
        proc = subprocess.Popen(args, stdin = subprocess.PIPE,
                                stdout = stdout, stderr = subprocess.STDOUT)
        proc.stdin.write(json.dumps(d))
        proc.stdin.close()
        return LocalDetachedJob(self.node_id, proc)
