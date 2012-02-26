"""
    sci.job
    ~~~~~~~

    Simple Continuous Integration

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
from optparse import OptionParser
import re, os, time, sys, types, subprocess, logging, json
from .environment import Environment
from .artifacts import Artifacts
from .agents import Agents
from .session import Session
from .bootstrap import Bootstrap
from .http_client import HttpClient
from .slog import (StepBegun, StepFunDone, StepJoined, JobBegun, JobDone,
                   JobErrorThrown, SetDescription)


re_var = re.compile("{{(.*?)}}")


class JobException(Exception):
    pass


class JobFunction(object):
    def __init__(self, name, fun, **kwargs):
        self.name = name
        self.fun = fun
        self.is_main = False

    def __call__(self, *args, **kwargs):
        return self.fun(*args, **kwargs)


class Step(JobFunction):
    def __init__(self, job, name, fun, **kwargs):
        JobFunction.__init__(self, name, fun, **kwargs)
        self.job = job

    def __call__(self, *args, **kwargs):
        self.job.slog(StepBegun(self.name, args, kwargs))
        time_start = time.time()
        self.job._current_step = self
        self.job._print_banner("Step: '%s'" % self.name)
        ret = self.fun(*args, **kwargs)
        time_fun = time.time()
        self.job.slog(StepFunDone(self.name, time_fun - time_start))

        # Wait for any unfinished detached jobs
        if self.job.agents.should_run():
            self.job.agents.run()
            time_joined = time.time()
            self.job.slog(StepJoined(self.name, time_joined - time_fun))
        return ret


class MainFn(JobFunction):
    def __init__(self, name, fun, **kwargs):
        JobFunction.__init__(self, name, fun, **kwargs)
        self.is_main = True


class Job(object):
    def __init__(self, import_name, debug = False):
        self._import_name = import_name
        # The session is known when running - not this early
        self._session = None
        self.steps = []
        self._mainfn = None
        self._description = ""
        self.build_id = None
        self.debug = debug
        self._job_key = os.environ.get("SCI_JOB_KEY")
        self._current_step = None

        self.env = Environment()
        self._default_fns = {}
        self.artifacts = Artifacts(self, "http://localhost:6698")
        self.agents = Agents(self, "http://localhost:6697")
        self.jobserver = "http://localhost:6697"

    def set_description(self, description):
        self._description = self.format(description)
        self.slog(SetDescription(self._description))

    def get_description(self):
        return self._description

    description = property(get_description, set_description)

    def set_session(self, session):
        if self._session:
            raise JobException("The session can only be set once")
        self._session = session

    def get_session(self):
        return self._session

    session = property(get_session, set_session)

    ### Decorators ###

    def default(self, name, **kwargs):
        def decorator(f):
            self._default_fns[name] = f
            return f
        return decorator

    def step(self, name, **kwargs):
        def decorator(f):
            s = Step(self, name, f, **kwargs)
            self.steps.append(s)
            return s
        return decorator

    def main(self, **kwargs):
        def decorator(f):
            fn = MainFn('main', f)
            self._mainfn = fn
            return fn
        return decorator

    def _timestr(self):
        delta = int(time.time() - self.start_time)
        if delta > 59:
            return "%dm%d" % (delta / 60, delta % 60)
        return "%d" % delta

    def _print_banner(self, text, dash = "-"):
        prefix = "[+%s]" % self._timestr()
        dash_left = (80 - len(text) - 4 - len(prefix)) / 2
        dash_right = 80 - len(text) - 4 - len(prefix) - dash_left
        print("%s%s[ %s ]%s" % (prefix, dash * dash_left,
                                 text, dash * dash_right))

    def _parse_arguments(self, params):
        # Parse parameters
        parser = OptionParser()
        (opts, args) = parser.parse_args()

        # Parse parameters specified as args:
        for arg in args:
            if "=" in arg:
                k, v = arg.split("=", 2)
                params[k] = v

    def _start(self, env, session, entrypoint, args, kwargs):
        # Must set time first. It's used when printing
        self.start_time = time.time()
        self.session = session
        self.build_id = env['SCI_BUILD_ID']
        self.env = env

        if entrypoint.is_main:
            for name in self._default_fns:
                if not name in env:
                    env[name] = self._default_fns[name]()

        self.slog(JobBegun())
        self._print_banner("Preparing Job", dash = "=")

        print("Build-Id: %s" % self.build_id)
        self.env.print_values()

        self._print_banner("Starting Job", dash = "=")
        ret = entrypoint.fun(*args, **kwargs)
        self._print_banner("Job Finished", dash = "=")
        self.slog(JobDone())
        return ret

    def slog(self, item):
        url = '/slog/%s' % self.session.id
        HttpClient(self.jobserver).call(url, input = item.serialize(), raw = True)

    def start(self, params = {}):
        """Start a job manually (for testing)

           This method is only used when running a job manually by
           invoking the job's script from the command line."""
        logging.basicConfig(level=logging.DEBUG)
        client = HttpClient(self.jobserver)

        # The build will contain all information necessary to build it,
        # also including parameters. Gather all those
        self._parse_arguments(params)

        # Save the recipe at the job server
        contents = open(sys.modules[self._import_name].__file__, "rb").read()
        result = client.call("/recipe/private.json",
                             input = json.dumps({"contents": contents}))
        recipe_id = result['ref']

        # Update the job to use this recipe and lock it to a ref
        contents = {'recipe_name': 'private',
                    'recipe_ref': recipe_id}
        result = client.call("/job/private",
                             input = json.dumps({"contents": contents}))
        job_ref = result['ref']

        # Create a build
        build_info = client.call('/build/create/private.json',
                                 input = json.dumps({'job_ref': job_ref,
                                                     'parameters': params}))
        session = Session.create(build_info['session_id'])

        return Bootstrap.run(session, build_id = build_info['id'],
                             jobserver = self.jobserver)

    def run(self, cmd, **kwargs):
        """Runs a command in a shell

           The command will be run with the current working directory
           set to be the session's workspace.

           If the command fails, this method will raise an error
        """
        cmd = self.format(cmd, **kwargs)
        devnull = open("/dev/null", "r")
        p = subprocess.Popen(cmd,
                             shell = True,
                             stdin = devnull, stdout = sys.stdout,
                             stderr = sys.stderr,
                             cwd = self.session.workspace)
        p.communicate()
        if p.returncode != 0:
            self.error("Command failed")

    def _format(self, tmpl, **kwargs):
        while True:
            m = re_var.search(tmpl)
            if not m:
                break
            name = m.groups()[0]
            value = self.var(name, **kwargs)
            if not value:
                self.error("Failed to replace template variable %s" % name)
            tmpl = tmpl.replace("{{%s}}" % name, str(value))
        return tmpl

    def format(self, tmpl, **kwargs):
        if isinstance(tmpl, basestring):
            return self._format(tmpl, **kwargs)
        elif isinstance(tmpl, types.ListType):
            return [self._format(t, **kwargs) for t in tmpl]
        else:
            raise TypeError("Invalid type for format")

    def var(self, _key, **kwargs):
        value = kwargs.get(_key)
        if not value:
            value = self.env.get(_key)
        return value

    def error(self, what):
        self.slog(JobErrorThrown(what))
        raise JobException(what)
