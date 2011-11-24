#!/usr/bin/env python
#
# Syntax: ./run_job <session-id>
#
# It should be run with the current working directory set properly
#
import sys, json
from sci.session import Session
from sci.bootstrap import Bootstrap

data = json.loads(sys.stdin.read())

session_id = sys.argv[1]
session = Session.load(session_id)

Bootstrap.run(session, data["build_id"], "http://localhost:6697", data["funname"],
              args = data["args"], kwargs = data["kwargs"], env = data["env"])
