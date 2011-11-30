"""
    sci.job
    ~~~~~~~

    Simple Continuous Integration

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
from optparse import OptionParser
import re, os, socket, time, sys, types, subprocess, logging, json
from datetime import datetime
from .config import Config
from .environment import Environment
from .params import Parameters, ParameterError
from .artifacts import Artifacts
from .agents import Agents
from .session import Session
from .bootstrap import Bootstrap
from .http_client import HttpClient


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
        self.job._current_step = self
        self.job._print_banner("Step: '%s'" % self.name)
        ret = self.fun(*args, **kwargs)
        # Wait for any unfinished detached jobs
        self.job.agents.run()
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

        self.env = self._create_environment()
        self._params = Parameters(self.env)
        self.artifacts = Artifacts(self, "http://localhost:6698")
        self.agents = Agents(self, "http://localhost:6699")
        self.jobserver = "http://localhost:6697"

    def set_description(self, description):
        self._description = self.format(description)

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

    def parameter(self, name, description = "", default = None,
                  **kwargs):
        param = self._params.declare(name, description = description,
                                     default = default, **kwargs)
        self.env.define(name, description, source = "parameter", final = True)
        return param

    def _create_environment(self):
        env = Environment()

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

    ### Decorators ###

    def default(self, what, **kwargs):
        def decorator(f):
            what.default = f
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
        parser.add_option("--list-parameters", dest = "list_parameters",
                          action = "store_true",
                          help = "List job parameters and quit")
        (opts, args) = parser.parse_args()

        if opts.list_parameters:
            self._params.print_help()
            sys.exit(2)
        # Parse parameters specified as args:
        for arg in args:
            if "=" in arg:
                k, v = arg.split("=", 2)
                params[k] = v

    def _start(self, session, entrypoint, params, args,
               kwargs, env, build_id, build_name):
        # Must set time first. It's used when printing
        self.start_time = time.time()
        self.session = session
        self.build_id = build_id
        if entrypoint.is_main:
            self.env.define("SCI_BUILD_ID", "The unique build identifier",
                            read_only = True, source = "initial environment",
                            value = self.build_id)
            self.env.define("SCI_BUILD_NAME", "The unique build name",
                            read_only = True, source = "initial environment",
                            value = build_name)
            # Set parameters
            for k in params:
                self.env[k] = params[k]

            try:
                self._params.evaluate()
            except ParameterError as e:
                print("error: %s " % e)
                print("")
                print("Run with --list-parameters to list them.")
                sys.exit(2)

        self._print_banner("Preparing Job", dash = "=")

        # Read global config file
        config = Config.from_pyfile(os.path.join(session.path, 'config.py'))
        if config:
            self.env.merge(config)

        # Merge environments
        if env:
            self.env.merge(env)

        print("Build-Id: %s" % self.build_id)
        self.env.print_values()

        self._print_banner("Starting Job", dash = "=")
        ret = entrypoint.fun(*args, **kwargs)
        self._print_banner("Job Finished", dash = "=")
        return ret

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

        # Update the job to use this recipe
        contents = {'recipe': recipe_id}
        result = client.call("/job/private.json",
                             input = json.dumps({"contents": contents}))
        job_ref = result['ref']

        # Create a build
        build_info = client.call('/build/create/%s.json' % job_ref,
                                 input = json.dumps({'parameters': params}))
        session = Session.create()

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
        raise JobException(what)
