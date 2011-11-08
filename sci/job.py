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
        self.params = Parameters()
        self.config = Config()
        self.env = Environment()
        self.artifacts = Artifacts(self)
        self.debug = debug
        self._set_default_env()
        self._master_url = os.environ.get("SCI_MASTER_URL")
        self._job_key = os.environ.get("SCI_JOB_KEY")
        self._spawned_sub_nodes = 0
        self._current_step = None

        self.last_slave = 0

    def _allocate_node(self):
        if 1 == 1:
            self.last_slave += 1
            return RemoteNode("S%d" % self.last_slave,
                              "http://127.0.0.1:%d" % (6700 + self.last_slave))
        if self._master_url is None:
            # Can not allocate a node - use local node
            self._spawned_sub_nodes += 1
            return LocalNode("%s.%s" % (self.env["SCI_SERVER_ID"],
                                        self._spawned_sub_nodes))

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
        return self.params.declare(name, description = description,
                                   default = default, **kwargs)

    def _set_default_env(self):
        # Set hostname
        hostname = socket.gethostname()
        if hostname.endswith(".local"):
            hostname = hostname[:-len(".local")]
        self.env["SCI_HOSTNAME"] = hostname
        self.env["SCI_SERVER_ID"] = os.environ.get("SCI_SERVER_ID", "S0")
        now = datetime.now()
        self.env["SCI_DATETIME"] = now.strftime("%Y-%m-%d_%H-%M-%S")

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
        prefix = "[%s +%s]" % (self.env["SCI_SERVER_ID"], self._timestr())
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
        print("Configuration Values:")
        for key in sorted(self.config):
            print("  %s: %s" % (key, strfy(self.config[key])))
        print("Parameters:")
        for key in sorted(self.params):
            print("  %s: %s" % (key, strfy(self.params[key])))
        print("Initial Environment:")
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
            self.config.from_pyfile(opts.config)
        if opts.list_parameters:
            self.params.print_help()
            sys.exit(2)
        # Parse parameters specified as args:
        for arg in args:
            if "=" in arg:
                k, v = arg.split("=", 2)
                self.params[k] = v
        return opts, args

    def _start(self, entrypoint, session = None, use_argv = True, params = {}, env = {}, config = {}, validate_params = False, args = [], kwargs = {}):
        if session:
            self.session = session
        if use_argv:
            opts, _ = self._parse_arguments()
        # Must set time first. It's used when printing
        self.start_time = time.time()
        self._print_banner("Preparing Job", dash = "=")
        # Read global config file
        if self.config.from_env("SCI_CONFIG"):
            print("Loaded configuration from %s" % os.environ["SCI_CONFIG"])

        # Override parameters/env/config
        for k in env:
            self.env[k] = env[k]
        for k in params:
            self.params[k] = params[k]
        for k in config:
            self.config[k] = config[k]

        if validate_params:
            try:
                self.params.evaluate()
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
                     env, params, config, node_id):
        return self._start(entrypoint, session = session,
                           params = params, env = env, config = config,
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
            value = self.get_var(name, args = kwargs)
            if not value:
                self.error("Failed to replace template variable %s" % name)
            tmpl = tmpl.replace("{{%s}}" % name, str(value))
        return tmpl

    def get_var(self, name, args = {}):
        value = args.get(name)
        if not value:
            value = self.params.get(name)
        if not value:
            value = self.env.get(name)
        if not value:
            value = self.config.get(name)
        return value

    def error(self, what):
        raise JobException(what)
