#!/usr/bin/env python
import sys, json
from sci.job import JobLocation
from sci.session import Session
from sci.bootstrap import run_package

data = json.loads(sys.stdin.read())

if "_path" in data:
    Session.set_root_path(data["_path"])

location = JobLocation(data["location"]["package"],
                       data["location"]["filename"])

session = Session.load(data["sid"])
run_package(session, location, data["funname"],
            args = data["args"], kwargs = data["kwargs"],
            env = data["env"])
