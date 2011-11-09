"""
    sci.job
    ~~~~~~~

    Simple Continuous Integration

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
from optparse import OptionParser
import types, re, os, socket, time, sys
from datetime import datetime
from .config import Config
from .environment import Environment
from .params import Parameters, ParameterError
from .node import LocalNode, RemoteNode
from .artifacts import Artifacts
from .session import Session

re_var = re.compile("{{(.*?)}}")


class JobException(Exception):
    pass


class Step(object):
    def __init__(self, job, name, fun, **kwargs):
        self.job = job
        self.name = name
        self.fun = fun
        self.detached_jobs = []

    def __call__(self, *args, **kwargs):
        self.job._current_step = self
        self.job._print_banner("Step: '%s'" % self.name)
        ret = self.fun(*args, **kwargs)
        # Wait for any unfinished detached jobs
        for job in self.detached_jobs:
            job.join()
            self.job._print_banner("%s finished" % job.session_id)
        self.detached_jobs = []
        return ret

    def async(self, *args, **kwargs):
        node = self.job._allocate_node()
        self.job._print_banner("Detach: '%s' -> %s" % (self.name, node.node_id))
        rjob = node.run(self.job, self.fun, args, kwargs)
        self.job._current_step.detached_jobs.append(rjob)
        return rjob


class Job(object):
    def __init__(self, import_name, debug = False):
        self._import_name = import_name
        # The session is known when running - not this early
        self._session = None
        self.steps = []
        self._mainfn = None
        self._description = ""
        self.env = self._create_environment()
        self._params = Parameters(self.env)
        self.artifacts = Artifacts(self)
        self.debug = debug
        self._master_url = os.environ.get("SCI_MASTER_URL")
        self._job_key = os.environ.get("SCI_JOB_KEY")
        self._spawned_sub_nodes = 0
        self._current_step = None

        self.last_slave = 0

    def _allocate_node(self):
        if 0 == 1:
            self.last_slave += 1
            return RemoteNode("S%d" % self.last_slave,
                              "http://127.0.0.1:%d" % (6700 + self.last_slave))
        if self._master_url is None:
            # Can not allocate a node - use local node
            self._spawned_sub_nodes += 1
            return LocalNode("")

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
            self.steps.append((name, f))
            return Step(self, name, f, **kwargs)
        return decorator

    def main(self, **kwargs):
        def decorator(f):
            self._mainfn = f
            return f
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

    def _print_vars(self):
        def strfy(v):
            if (type(v)) in types.StringTypes:
                return "'%s'" % v
            return str(v)
        # Print out all parameters, config and the environment
        print("Session ID: %s" % self.session.id)
        print("Environment:")
        for key in sorted(self.env):
            print("  %s: %s" % (key, strfy(self.env[key])))

    def _parse_arguments(self):
        # Parse parameters
        parser = OptionParser()
        parser.add_option("-c", "--config", dest = "config",
                          help = "configuration file to use")
        parser.add_option("--list-parameters", dest = "list_parameters",
                          action = "store_true",
                          help = "List job parameters and quit")
        (opts, args) = parser.parse_args()
        if opts.config:
            self.env.merge(Config.from_pyfile(opts.config))

        if opts.list_parameters:
            self._params.print_help()
            sys.exit(2)
        # Parse parameters specified as args:
        for arg in args:
            if "=" in arg:
                k, v = arg.split("=", 2)
                self.env[k] = v
        return opts, args

    def _start(self, entrypoint, session = None, use_argv = True, env = {}, params = {}, validate_params = False, args = [], kwargs = {}):
        if session:
            self.session = session
        if use_argv:
            opts, _ = self._parse_arguments()
        # Must set time first. It's used when printing
        self.start_time = time.time()
        self._print_banner("Preparing Job", dash = "=")

        # Read global config file
        config = Config.from_env("SCI_CONFIG")
        if config:
            self.env.merge(config)
            print("Loaded configuration from %s" % os.environ["SCI_CONFIG"])

        # Merge environments
        if env:
            self.env.merge(env)

        # Set parameters
        for k in params:
            self.env[k] = params[k]

        if validate_params:
            try:
                self._params.evaluate()
            except ParameterError as e:
                print("error: %s " % e)
                print("")
                print("Run with --list-parameters to list them.")
                sys.exit(2)
        self._print_vars()
        self._print_banner("Starting Job", dash = "=")
        ret = entrypoint(*args, **kwargs)
        self._print_banner("Job Finished", dash = "=")
        return ret

    def start(self, use_argv = True, params = {}):
        return self._start(self._mainfn, session = Session(),
                           use_argv = use_argv, params = params,
                           validate_params = True)

    def start_subjob(self, session, entrypoint, args, kwargs,
                     env):
        return self._start(entrypoint, session = session,
                           env = env,
                           args = args, kwargs = kwargs)

    def run(self, cmd, **kwargs):
        if self.debug:
            print("Running CMD '%s'" % self.format(cmd, **kwargs))
        time.sleep(1)

    def format(self, tmpl, **kwargs):
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

    def var(self, _key, **kwargs):
        value = kwargs.get(_key)
        if not value:
            value = self.env.get(_key)
        return value

    def error(self, what):
        raise JobException(what)
