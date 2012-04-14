"""
    sci.bootstrap
    ~~~~~~~~~~~~~

    SCI Bootstrap


    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
import os, shutil, imp, sys, socket
from datetime import datetime
from .session import Session
from .environment import Environment
from .http_client import HttpClient, HttpRequest


class Bootstrap(object):
    @classmethod
    def _find_job(cls, module):
        from .job import Job
        # Find the 'job' variable
        for k in dir(module):
            var = getattr(module, k)
            if issubclass(var.__class__, Job):
                return var
        raise Exception("Couldn't locate the Job variable")

    @classmethod
    def _find_entrypoint(cls, job, name):
        if not name:
            return job._mainfn
        for step in job.steps:
            if step.fun.__name__ == name:
                return step
        raise Exception("Couldn't locate entry point")

    @classmethod
    def get_url(cls, jobserver, url, dest_fname):
        with HttpRequest(jobserver, url) as src:
            with open(dest_fname, "wb") as dest:
                shutil.copyfileobj(src, dest)

    @classmethod
    def create_env(cls, parameters, build_uuid, build_name):
        env = Environment()

        for param in parameters:
            env[param] = parameters[param]

        env.define("SCI_BUILD_UUID", "The unique build identifier",
                   read_only = True, source = "initial environment",
                   value = build_uuid)
        env.define("SCI_BUILD_NAME", "The unique build name",
                   read_only = True, source = "initial environment",
                   value = build_name)

        hostname = socket.gethostname()
        if hostname.endswith(".local"):
            hostname = hostname[:-len(".local")]
        env.define("SCI_HOSTNAME", "Host Name", read_only = True,
                   value = hostname, source = "initial environment")

        now = datetime.now()
        env.define("SCI_DATETIME", "The current date and time",
                   read_only = True, source = "initial environment",
                   value = now.strftime("%Y-%m-%d_%H-%M-%S"))

        return env

    @classmethod
    def run(cls, job_server, session_id):
        session = Session.load(session_id)
        js = HttpClient(job_server)

        # Fetch all info necessary
        info = js.call('/build/session/%s' % session_id)

        recipe_fname = os.path.join(session.path, 'build.py')
        with open(recipe_fname, 'w') as f:
            f.write(info['recipe'])

        run_info = info['run_info']
        env = run_info.get('env')
        if env:
            env = Environment.deserialize(env)
        else:
            env = Bootstrap.create_env(info['parameters'], info['build_uuid'],
                                       info['build_name'])

        mod = imp.new_module('recipe')
        mod.__file__ = recipe_fname
        execfile(recipe_fname, mod.__dict__)

        job = Bootstrap._find_job(mod)
        job.jobserver = job_server
        entrypoint = Bootstrap._find_entrypoint(job, run_info.get('step_fun'))

        args = run_info.get('args', [])
        kwargs = run_info.get('kwargs', {})
        ret = job._start(env, session, entrypoint, args, kwargs)

        # Update the session
        session = Session.load(session.id)
        session.return_value = ret
        session.return_code = 0  # We finished without exceptions.
        session.state = "finished"
        session.save()
        return ret
