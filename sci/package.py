"""
    sci.package
    ~~~~~~~~~~~

    SCI Package

    The job script is packaged into a zip file (here simply
    called 'package') together with all other files it needs.

    The package is then distributed to build slaves.

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
import zipfile, time, os
from tempfile import NamedTemporaryFile
from zipimport import zipimporter
from .session import Session
from .environment import Environment
from .utils import random_sha1


def _should_archive(root, directory):
    if os.path.exists(os.path.join(root, directory, "_do_not_package.txt")):
        return False
    return True


class Package(object):
    def __init__(self, fname):
        self.fname = fname

    def _find_job(self, module):
        from .job import Job
        # Find the 'job' variable
        for k in dir(module):
            var = getattr(module, k)
            if issubclass(var.__class__, Job):
                return var
        raise Exception("Couldn't locate the Job variable")

    def _find_entrypoint(self, job, name):
        if not name:
            return job._mainfn
        for step in job.steps:
            if step[1].__name__ == name:
                return step[1]
        raise Exception("Couldn't locate entry point")

    def run(self, session, script_fname, entrypoint_name = "",
            params = {}, args = [], kwargs = {}, env = None, flags = {}):
        # Hard-link or copy the package to the session directory
        dest_package = os.path.join(session.path, "packaged-job.zip")
        os.link(self.fname, dest_package)

        zmod = zipimporter(dest_package)
        mod = zmod.load_module(script_fname.replace(".py", ""))

        job = self._find_job(mod)
        entrypoint = self._find_entrypoint(job, entrypoint_name)

        if env:
            env = Environment.deserialize(env)

        from .job import JobLocation
        job.location = JobLocation(self.fname, script_fname)
        ret = job._start(session, entrypoint, params, args, kwargs, env, flags)

        # Update the session
        session = Session.load(session.id)
        session.return_value = ret
        session.return_code = 0  # We finished without exceptions.
        session.state = "finished"
        session.save()
        return ret

    @classmethod
    def create(self, srcdir, output_dir):
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        rand = random_sha1()[0:7]
        basename = "private-%s-%s.zip" % (time.strftime("%y%m%d_%H%M%S"), rand)
        destfname = os.path.join(output_dir, basename)
        with NamedTemporaryFile(dir = os.path.dirname(destfname),
                                delete = False) as f:
            zf = zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED)
            for root, dirnames, filenames in os.walk(srcdir):
                dirnames[:] = [d for d in dirnames if _should_archive(root, d)]
                for filename in filenames:
                    filename = os.path.realpath(os.path.join(root, filename))
                    zf.write(filename, os.path.relpath(filename, srcdir))
            zf.close()
            os.rename(f.name, destfname)
            return Package(destfname)
        raise Exception("Failed to create package")
