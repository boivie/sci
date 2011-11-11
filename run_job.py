#!/usr/bin/env python
#
# Syntax: ./run_job <session-id>
#
# It should be run with the current working directory set properly
#
import sys, json, os
from sci.session import Session
from sci.package import Package

data = json.loads(sys.stdin.read())

session_id = sys.argv[1]
session = Session.load(session_id)

package_fname = os.path.join(os.curdir, "packages", data["location"]["package"])
package = Package(package_fname)

package.run(session, data["location"]["filename"], data["funname"],
            args = data["args"], kwargs = data["kwargs"],
            env = data["env"])
