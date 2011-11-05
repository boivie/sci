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
from .node import Node
from .artifacts import Artifacts

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
        self.job.current_step = self
        self.job.print_banner("Step: '%s'" % self.name)
        ret = self.fun(*args, **kwargs)
        # Wait for any detached jobs
        for job in self.detached_jobs:
            job.wait()
        self.detached_jobs = []
        return ret

    def run_detached(self, *args, **kwargs):
        self.job.print_banner("Detach: '%s'" % self.name)
        node = self.job.allocate_node()
        rjob = node.run(self.job, self.fun, args, kwargs)
        self.job.current_step.detached_jobs.append(rjob)


class Job(object):
    def __init__(self, import_name, debug = False):
        self.import_name = import_name
        self.steps = []
        self.mainfn = None
        self.description = ""
        self.params = Parameters()
        self.config = Config()
        self.env = Environment()
        self.artifacts = Artifacts(self)
        self.debug = debug
        self.set_default_env()
        self.master_url = os.environ.get("SCI_MASTER_URL")
        self.job_key = os.environ.get("SCI_JOB_KEY")
        self.spawned_sub_nodes = 0
        self.current_step = None

    def allocate_node(self):
        if self.master_url is None:
            # Can not allocate a node - use local node
            self.spawned_sub_nodes += 1
            return Node("%s.%s" % (self.env["SCI_SERVER_ID"],
                                   self.spawned_sub_nodes),
                        "local", None)

    def set_description(self, description):
        self.description = description

    def parameter(self, name, description = "", default = None,
                  **kwargs):
        return self.params.declare(name, description = description,
                                   default = default, **kwargs)

    def set_default_env(self):
        # Set hostname
        hostname = socket.gethostname()
        if hostname.endswith(".local"):
            hostname = hostname[:-len(".local")]
        self.env["SCI_HOSTNAME"] = hostname
        self.env["SCI_SERVER_ID"] = os.environ.get("SCI_SERVER_ID", "S0")
        now = datetime.now()
        self.env["SCI_DATETIME"] = now.strftime("%Y-%m-%d_%H-%M-%S")

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
            self.mainfn = f
            return f
        return decorator

    def timestr(self):
        delta = int(time.time() - self.start_time)
        if delta > 59:
            return "%dm%d" % (delta / 60, delta % 60)
        return "%d" % delta

    def print_banner(self, text, dash = "-"):
        prefix = "[%s +%s]" % (self.env["SCI_SERVER_ID"], self.timestr())
        dash_left = (80 - len(text) - 4 - len(prefix)) / 2
        dash_right = 80 - len(text) - 4 - len(prefix) - dash_left
        print("%s%s[ %s ]%s" % (prefix, dash * dash_left,
                                 text, dash * dash_right))

    def print_vars(self):
        def strfy(v):
            if (type(v)) in types.StringTypes:
                return "'%s'" % v
            return str(v)
        # Print out all parameters, config and the environment
        print("Configuration Values:")
        for key in sorted(self.config):
            print("  %s: %s" % (key, strfy(self.config[key])))
        print("Parameters:")
        for key in sorted(self.params):
            print("  %s: %s" % (key, strfy(self.params[key])))
        print("Initial Environment:")
        for key in sorted(self.env):
            print("  %s: %s" % (key, strfy(self.env[key])))

    def parse_arguments(self):
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

    def start(self, use_argv = True, **kwargs):
        if use_argv:
            opts, args = self.parse_arguments()
        # Must set time first. It's used when printing
        self.start_time = time.time()
        self.print_banner("Preparing Job", dash = "=")
        # Read global config file
        if self.config.from_env("SCI_CONFIG"):
            print("Loaded configuration from %s" % os.environ["SCI_CONFIG"])

        # Set parameters given to 'start':
        for k in kwargs:
            self.params[k] = kwargs[k]

        try:
            self.params.evaluate()
        except ParameterError as e:
            print("error: %s " % e)
            print("")
            print("Run with --list-parameters to list them.")
            sys.exit(2)
        self.print_vars()
        self.print_banner("Starting Job", dash = "=")
        self.mainfn()
        self.print_banner("Job Finished", dash = "=")

    def start_subjob(self, fun, args, kwargs, env, params, config, node_id):
        self.start_time = time.time()
        for k in env:
            self.env[k] = env[k]
        for k in params:
            self.params[k] = params[k]
        for k in config:
            self.config[k] = config[k]
        self.env["SCI_SERVER_ID"] = node_id

        self.print_banner("Starting Detached Job", dash = "=")
        for step in self.steps:
            if step[1].__name__ == fun:
                step[1](*args, **kwargs)
        self.print_banner("Detached Job Finished", dash = "=")

    def run(self, cmd, args = {}, **kwargs):
        if self.debug:
            print("Running CMD '%s'" % self.format(cmd, args))
        time.sleep(0.1)

    def format(self, tmpl, args = {}):
        while True:
            m = re_var.search(tmpl)
            if not m:
                break
            name = m.groups()[0]
            value = self.get_var(name, args = args)
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
