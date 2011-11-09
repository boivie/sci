"""
    sci.parameters
    ~~~~~~~~~~~~~~

    Parameter Handling

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
import types


class ParameterError(Exception):
    pass


class Parameter(object):
    def __init__(self, env, name, **kwargs):
        self.env = env
        self.name = name
        self.description = kwargs.get("description", "")
        self.required = kwargs.get("required", False)
        self.default = kwargs.get("default", None)
        self.type = type

    def __call__(self):
        return self.env.get(self.name)

    def evaluate(self):
        if not self.name in self.env and self.default:
            if type(self.default) is types.FunctionType:
                self.env[self.name] = self.default()
            else:
                self.env[self.name] = self.default


class Parameters(object):
    def __init__(self, env):
        self.__declared = []
        self.env = env
        pass

    def declare(self, name, **kwargs):
        obj = Parameter(self.env, name, **kwargs)
        self.__declared.append(obj)
        return obj

    def declared(self):
        return self.__declared

    def evaluate(self, initial = {}):
        # Sanity check
        for p in self.__declared:
            if p.required and p.default:
                raise ParameterError("You can not specify a default value" +
                                     "for a required parameter")
        # Set initial values
        for k in initial:
            self.env[k] = initial[k]

        # Verify that all required parameters are set
        for p in self.__declared:
            if p.required and not p.name in self.env:
                raise ParameterError("Required parameter not set: " +
                                     "'%s'" % p.name)

        # Use default parameters if necessary
        for param in self.declared():
            param.evaluate()

    def print_help(self):
        print("Parameters declared for this job:")
        for p in self.declared():
            s = p.name
            if p.required:
                s += " [required]"
            elif p.default:
                if type(p.default) is types.FunctionType:
                    s += " (*)"
                else:
                    s += " (%s)" % p.default
            if len(s) > 28:
                print("  " + s)
                print("  " + " " * 30 + p.description)
            else:
                print("  %s%s%s" % (s, " " * max(2, 30 - len(s)), p.description))
        print("")
        print("Parameters marked with (*) will be calculated if not set.")
