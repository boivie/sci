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
        self._return_value = None
        self._has_finished = False

    def join(self):
        """Blocks until the job has finished.

           Does not return anything."""
        if self._has_finished:
            return
        self._join()

    def _join(self):
        """Method that should be overridden

           When it finishes, it must call _finished()"""
        while not self._poll():
            time.sleep(0.5)

    def _finished(self, return_value):
        self._return_value = return_value
        self._has_finished = True

    def poll(self):
        """Checks if the job has finished

           Will return True if it has finished or False if it
           still running. This function can be called multiple
           times."""
        if self._has_finished:
            return True
        return self._poll()

    def _poll(self):
        """Method that should be overridden

           When it finishes, it must called _finished()"""
        raise NotImplemented()

    def get(self):
        """Returns the result value of the job.

           It will block until the job is finished. Use 'poll'
           to know when it's finished"""
        self.join()
        return self._return_value


class Node(object):
    """Represents a node"""
    def _serialize(self, job, fun, args, kwargs):
        return {"location": {"package": job.location.package,
                             "filename": job.location.filename},
                "funname": fun.__name__,
                "args": args,
                "kwargs": kwargs,
                "env": job.env.serialize()}

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
        self.return_code = None

    def _join(self):
        self.proc.wait()
        s = Session.load(self.session_id)
        self._finished(s.return_value)

    def _poll(self):
        return_code = self.proc.poll()
        if return_code is None:
            return False

        s = Session.load(self.session_id)
        self.return_code = return_code
        self._finished(s.return_value)
        return True


class LocalNode(Node):
    def run_remote(self, data, local_path = None):
        # Create a session
        session = Session.create()
        d = json.loads(data)
        d["sid"] = session.id
        d["_path"] = local_path
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

    def _join(self):
        ret = self.client.call("/info/%s.json" % self.session_id, block = 1)
        self._finished(ret.get("return_value"))

    def _poll(self):
        ret = self.client.call("/info/%s.json" % self.session_id)
        if ret["state"] == "running":
            return False
        self._finished(ret.get("return_value"))
        return True


class RemoteNode(Node):
    def __init__(self, url):
        self.client = HttpClient(url)

    def run_remote(self, data):
        ret = self.client.call("/start.json", input = data)
        if ret["status"] != "started":
            raise Exception("Bad status")
        return RemoteDetachedJob(ret["id"], self.client)
