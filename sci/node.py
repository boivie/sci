"""
    sci.node
    ~~~~~~~~

    Handle nodes

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
import sys, subprocess, json, time
from .session import Session
from .http_client import HttpClient


class DetachedJob(object):
    def __init__(self, session_id):
        self.session_id = session_id

    def join(self):
        while not self.poll():
            time.sleep(0.5)

    def poll(self):
        raise NotImplemented()


class Node(object):
    """Represents a node"""
    def __init__(self, node_id):
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
    def __init__(self, session_id, proc):
        super(LocalDetachedJob, self).__init__(session_id)
        self.proc = proc

    def join(self):
        return self.proc.wait()

    def poll(self):
        return self.proc.poll()


class LocalNode(Node):
    def run_remote(self, data):
        # Create a session
        session = Session.create()
        d = json.loads(data)
        d["sid"] = session.id
        args = ["./run_job.py"]
        stdout = open(session.logfile, "w")
        session.state = "running"
        session.save()
        proc = subprocess.Popen(args, stdin = subprocess.PIPE,
                                stdout = stdout, stderr = subprocess.STDOUT)
        proc.stdin.write(json.dumps(d))
        proc.stdin.close()
        return LocalDetachedJob(session.id, proc)


class RemoteDetachedJob(DetachedJob):
    def __init__(self, session_id, client):
        super(RemoteDetachedJob, self).__init__(session_id)
        self.client = client

    def poll(self):
        ret = self.client.call("/info/%s.json" % self.session_id)
        if ret["state"] == "running":
            return False
        return True


class RemoteNode(Node):
    def __init__(self, node_id, url):
        super(RemoteNode, self).__init__(node_id)
        self.client = HttpClient(url)

    def run_remote(self, data):
        ret = self.client.call("/start.json", input = data)
        if ret["status"] != "started":
            raise Exception("Bad status")
        return RemoteDetachedJob(ret["id"], self.client)
