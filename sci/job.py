"""
    sci.job
    ~~~~~~~

    Simple Continuous Integration

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
import types, re

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
    def __init__(self, name, fun, **kwargs):
        self.name = name
        self.fun = fun

    def __call__(self, *args, **kwargs):
        print("Runing step '%s' with %s" % (self.name, args))
        return self.fun(*args, **kwargs)

    def run_detached(self, *args, **kwargs):
        print("Runing DETACHED step '%s' (%s) with %s" % \
                  (self.name, self.fun, args))
        return self.fun(*args, **kwargs)


class Env(object):
    def __init__(self, job, name):
        self.job = job
        self.name = name

    def set(self, value):
        self.job.ENV[self.name] = value

    def __call__(self):
        return self.job.ENV.get(self.name)


class Job(object):
    def __init__(self, import_name):
        self.import_name = import_name
        self.named = {}
        self.ENV = {}
        self.PARAMETERS = {}
        self.steps = []
        self.mainfn = None
        self.description = ""

    def set_description(self, description):
        self.description = description

    def parameter(self, name, description = "", default = None,
                  **kwargs):
        p = Parameter(self, name, description, default, **kwargs)
        self.named[name] = p
        return p

    def env(self, name, **kwargs):
        e = Env(self, name, **kwargs)
        self.named[name] = e
        return e

    def default(self, what, **kwargs):
        def decorator(f):
            what.default = f
            return f
        return decorator

    def step(self, name, **kwargs):
        def decorator(f):
            self.steps.append((name, f))
            return Step(name, f, **kwargs)
        return decorator

    def main(self, **kwargs):
        def decorator(f):
            self.mainfn = f
            return f
        return decorator

    def start(self, **kwargs):
        print("Starting %s" % (self.import_name))
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
        self.mainfn()
        print("All done.")

    def store(self, filename):
        print("Storing '%s' on the storage node" % filename)

    def get_stored(self, filename):
        print("Retrieving stored '%s' from the storage node" % filename)

    def run(self, cmd, args = {}, **kwargs):
        print("Running CMD '%s'" % self._format(cmd, args))

    def _format(self, tmpl, args = {}):
        while True:
            m = re_var.search(tmpl)
            if not m:
                break
            name = m.groups()[0]
            value = args.get(name)
            if not value:
                value = self.PARAMETERS.get(name)
            if not value:
                value = self.ENV.get(name)
            if not value:
                self.error("Failed to replace template variable %s" % name)
            tmpl = tmpl.replace("{{%s}}" % name, value)
        return tmpl

    def error(self, what):
        raise JobException(what)

    def info(self):
        print("Job %s with main = %s" % (self.import_name, self.mainfn))
        print("Parameters:")
        for name in self.named:
            obj = self.named[name]
            if issubclass(Parameter, obj.__class__):
                print("  %s: %s" % (name, obj))
        print("Environment:")
        for name in self.named:
            obj = self.named[name]
            if issubclass(Env, obj.__class__):
                print("  %s: %s" % (name, obj))
