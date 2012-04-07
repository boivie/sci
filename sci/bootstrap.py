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
    def handle_parameters(cls, env, parameters, metadata):
        for param in parameters:
            if not param in metadata['Parameters']:
                print("Invalid parameter: %s" % param)
                sys.exit(2)
            env[param] = parameters[param]

        # Verify that all 'required' parameters are set
        for name in metadata['Parameters']:
            param = metadata['Parameters'][name]
            if param.get('required', False):
                if not name in env:
                    print("Required parameter %s not set!" % name)
                    sys.exit(2)

        # Set default parameters that have a static value
        # (parameters that have a function as default value will have them
        #  called just before starting the job)
        for name in metadata['Parameters']:
            param = metadata['Parameters'][name]
            if 'default' in param and not name in env:
                env[name] = param['default']

    @classmethod
    def create_env(cls, metadata, parameters, build_id, build_name):
        env = Environment()

        # Set provided parameters
        Bootstrap.handle_parameters(env, parameters, metadata)

        env.define("SCI_BUILD_ID", "The unique build identifier",
                   read_only = True, source = "initial environment",
                   value = build_id)
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
    def run(cls, session, build_id, jobserver, entrypoint_name = "",
            args = [], kwargs = {}, env = None):
        # Fetch build information
        build_info = HttpClient(jobserver).call('/build/%s.json' % build_id)
        build_info = build_info['build']

        # Fetch the recipe and metadata
        recipe_ref = build_info['recipe_ref']
        recipe_fname = os.path.join(session.path, 'build.py')
        recipe = HttpClient(jobserver).call('/recipe/%s.json' % recipe_ref)
        with open(recipe_fname, 'w') as f:
            f.write(recipe['contents'])

        if env:
            env = Environment.deserialize(env)
        else:
            build_name = "%s-%d" % (build_info['job_name'],
                                    build_info['number'])
            env = Bootstrap.create_env(recipe['metadata'],
                                       build_info['parameters'],
                                       build_id, build_name)

        mod = imp.new_module('recipe')
        mod.__file__ = recipe_fname
        execfile(recipe_fname, mod.__dict__)

        job = Bootstrap._find_job(mod)
        entrypoint = Bootstrap._find_entrypoint(job, entrypoint_name)

        ret = job._start(env, session, entrypoint, args, kwargs)

        # Update the session
        session = Session.load(session.id)
        session.return_value = ret
        session.return_code = 0  # We finished without exceptions.
        session.state = "finished"
        session.save()
        return ret
