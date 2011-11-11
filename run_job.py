#!/usr/bin/env python
import sys, json, os
from sci.session import Session
from sci.package import Package

data = json.loads(sys.stdin.read())

package_fname = os.path.join(os.path.dirname(sys.modules["sci.job"].__file__),
                             "packages", data["location"]["package"])
package = Package(package_fname)

if "_path" in data:
    Session.set_root_path(data["_path"])

session = Session.load(data["sid"])
package.run(session, data["location"]["filename"], data["funname"],
            args = data["args"], kwargs = data["kwargs"],
            env = data["env"])
