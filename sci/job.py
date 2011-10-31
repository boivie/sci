"""
    sci.job
    ~~~~~~~

    Simple Continuous Integration

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
import types, re, os
from .config import Config
from .environment import Environment

re_var = re.compile("{{(.*?)}}")


class JobException(Exception):
    pass


class Parameter(object):
    def __init__(self, job, name, description, default,
                 required = False,
                 type = "string"):
        self.job = job
        self.name = name
        self.description = description
        self.required = required
        self.default = default
        self.type = type

    def __call__(self):
        return self.job.PARAMETERS.get(self.name)


class Step(object):
    def __init__(self, job, name, fun, **kwargs):
        self.job = job
        self.name = name
        self.fun = fun

    def __call__(self, *args, **kwargs):
        if self.job.debug:
            print("Runing step '%s' with %s" % (self.name, args))
        return self.fun(*args, **kwargs)

    def run_detached(self, *args, **kwargs):
        if self.job.debug:
            print("Runing DETACHED step '%s' (%s) with %s" % \
                      (self.name, self.fun, args))
        return self.fun(*args, **kwargs)


class Job(object):
    def __init__(self, import_name, debug = False):
        self.import_name = import_name
        self.named = {}
        self.PARAMETERS = {}
        self.steps = []
        self.mainfn = None
        self.description = ""
        self.config = Config()
        self.env = Environment()
        self.debug = debug

    def set_description(self, description):
        self.description = description

    def parameter(self, name, description = "", default = None,
                  **kwargs):
        p = Parameter(self, name, description, default, **kwargs)
        self.named[name] = p
        return p

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

    @classmethod
    def print_banner(cls, text):
        dash_left = (80 - len(text) - 4) / 2
        dash_right = 80 - len(text) - 4 - dash_left
        print("%s[ %s ]%s" % ("=" * dash_left, text, "=" * dash_right))

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
        for key in sorted(self.PARAMETERS):
            print("  %s: %s" % (key, strfy(self.PARAMETERS[key])))

    def start(self, **kwargs):
        self.print_banner("Preparing Job")
        # Read global config file
        if self.config.from_env("SCI_CONFIG"):
            print("Loaded configuration from %s" % os.environ["SCI_CONFIG"])

        for k in kwargs:
            self.PARAMETERS[k] = kwargs[k]
        # Set default parameters
        for name in self.named:
            obj = self.named[name]
            if issubclass(Parameter, obj.__class__):
                if not name in self.PARAMETERS and obj.default:
                    if type(obj.default) is types.FunctionType:
                        self.PARAMETERS[name] = obj.default()
                    else:
                        self.PARAMETERS[name] = obj.default
        self.print_vars()
        self.print_banner("Starting Job")
        self.mainfn()
        self.print_banner("Job Finished")

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
            value = self.PARAMETERS.get(name)
        if not value:
            value = self.env.get(name)
        if not value:
            value = self.config.get(name)
        return value

    def error(self, what):
        raise JobException(what)

    def info(self):
        print("Job %s with main = %s" % (self.import_name, self.mainfn))
        print("Parameters:")
        for name in self.named:
            obj = self.named[name]
            if issubclass(Parameter, obj.__class__):
                print("  %s: %s" % (name, obj))
