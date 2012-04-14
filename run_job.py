#!/usr/bin/env python
#
# Syntax: ./run_job
#
# It should be run with the current working directory set properly
#
import sys, json
from sci.bootstrap import Bootstrap

data = json.loads(sys.stdin.read())
Bootstrap.run(data['job_server'], data['session_id'])
