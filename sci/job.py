"""
    sci.job
    ~~~~~~~

    Simple Continuous Integration

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
import types, re, os, socket, time
from datetime import datetime
from .config import Config
from .environment import Environment
from .params import Parameters

re_var = re.compile("{{(.*?)}}")


class JobException(Exception):
    pass


class Step(object):
    def __init__(self, job, name, fun, **kwargs):
        self.job = job
        self.name = name
        self.fun = fun

    def __call__(self, *args, **kwargs):
        self.job.print_banner("Step: '%s'" % self.name)
        return self.fun(*args, **kwargs)

    def run_detached(self, *args, **kwargs):
        self.job.print_banner("Detach: '%s'" % self.name)
        return self.fun(*args, **kwargs)


class Job(object):
    def __init__(self, import_name, debug = False):
        self.import_name = import_name
        self.steps = []
        self.mainfn = None
        self.description = ""
        self.params = Parameters()
        self.config = Config()
        self.env = Environment()
        self.debug = debug
        self.set_default_env()
        self.master_url = os.environ.get("SCI_MASTER_URL")
        self.job_key = os.environ.get("SCI_JOB_KEY")

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

    def start(self, **kwargs):
        # Must set time first. It's used when printing
        self.start_time = time.time()
        self.print_banner("Preparing Job", dash = "=")
        # Read global config file
        if self.config.from_env("SCI_CONFIG"):
            print("Loaded configuration from %s" % os.environ["SCI_CONFIG"])

        self.params.evaluate(initial = kwargs)
        self.print_vars()
        self.print_banner("Starting Job", dash = "=")
        self.mainfn()
        self.print_banner("Job Finished", dash = "=")

    def store(self, filename):
        if self.debug:
            print("Storing '%s' on the storage node" % filename)

    def get_stored(self, filename):
        if self.debug:
            print("Retrieving stored '%s' from the storage node" % filename)

    def run(self, cmd, args = {}, **kwargs):
        if self.debug:
            print("Running CMD '%s'" % self.format(cmd, args))

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
