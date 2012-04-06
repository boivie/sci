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

run_info = data['run_info']
Bootstrap.run(session, data['build_id'], data['job_server'],
              run_info['step_fun'], args = run_info['args'],
              kwargs = run_info['kwargs'], env = run_info['env'])
