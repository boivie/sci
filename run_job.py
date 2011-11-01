#!/usr/bin/env python
import sys, json, imp


data = json.loads(sys.stdin.read())

d = imp.new_module('job')
d.__file__ = data["jobfname"]
execfile(data["jobfname"], d.__dict__)

# Find the 'job' variable
from sci.job import Job
for k in dir(d):
    var = getattr(d, k)
    if issubclass(var.__class__, Job):
        var.start_subjob(data["funname"], data["args"],
                         data["kwargs"],
                         data["env"], data["params"], data["config"],
                         data["node_id"])
