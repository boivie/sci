"""
    sci.bootstrap
    ~~~~~~~~~~~~~

    SCI Bootstrap


    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
import os, shutil, imp
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
    def run(cls, session, build_id, jobserver, entrypoint_name = "",
            args = [], kwargs = {}, env = None):
        # Fetch build information
        build_info = HttpClient(jobserver).call('/build/%s.json' % build_id)
        build_info = build_info['build']
        params = build_info["parameters"]

        # Fetch the recipe
        recipe = os.path.join(session.path, 'build.py')
        Bootstrap.get_url(jobserver,
                          '/recipe/%s.json' % build_info['recipe_ref'],
                          recipe)

        # Fetch configs
        config = os.path.join(session.path, 'config.py')
        Bootstrap.get_url(jobserver, '/config/master.txt', config)

        mod = imp.new_module('recipe')
        mod.__file__ = recipe
        execfile(recipe, mod.__dict__)

        job = Bootstrap._find_job(mod)
        entrypoint = Bootstrap._find_entrypoint(job, entrypoint_name)

        if env:
            env = Environment.deserialize(env)

        ret = job._start(session, entrypoint, params, args, kwargs,
                         env, build_id = build_id,
                         build_name = build_info['name'])

        # Update the session
        session = Session.load(session.id)
        session.return_value = ret
        session.return_code = 0  # We finished without exceptions.
        session.state = "finished"
        session.save()
        return ret
