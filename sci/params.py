"""
    sci.parameters
    ~~~~~~~~~~~~~~

    Parameter Handling

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
import types


class Parameter(object):
    def __init__(self, params, name, **kwargs):
        self.params = params
        self.name = name
        self.description = kwargs.get("description", "")
        self.required = kwargs.get("required", False)
        self.default = kwargs.get("default", None)
        self.type = type

    def __call__(self):
        return self.params.get(self.name)

    def evaluate(self):
        if not self.name in self.params and self.default:
            if type(self.default) is types.FunctionType:
                self.params[self.name] = self.default()
            else:
                self.params[self.name] = self.default


class Parameters(dict):
    def __init__(self):
        self.__declared = []
        pass

    def declare(self, name, **kwargs):
        obj = Parameter(self, name, **kwargs)
        self.__declared.append(obj)
        return obj

    def declared(self):
        return self.__declared
