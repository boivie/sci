#!/usr/bin/env python
import sys, json, imp
from sci.job import Job
from sci.session import Session
from sci.environment import Environment

data = json.loads(sys.stdin.read())

d = imp.new_module('job')
d.__file__ = data["jobfname"]
execfile(data["jobfname"], d.__dict__)

# Find the 'job' variable
for k in dir(d):
    var = getattr(d, k)
    if issubclass(var.__class__, Job):
        job = var
        session = Session.load(data["sid"])
        entrypoint = None
        for step in job.steps:
            if step[1].__name__ == data["funname"]:
                entrypoint = step[1]
                break
        if not entrypoint:
            job.error("No entry point given")

        env = Environment.deserialize(data["env"])
        ret = job.start_subjob(session = session,
                               entrypoint = entrypoint,
                               args = data["args"],
                               kwargs = data["kwargs"],
                               env = env)

        # Reload session in case it has stopped - doubtful.
        session = Session.load(data["sid"])
        session.return_value = ret
        session.return_code = 0  # We finished without exceptions.
        session.state = "finished"
        session.save()