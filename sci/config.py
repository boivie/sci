"""
    sci.config
    ~~~~~~~~~~

    Configuration Handling

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
import imp, os


class Config(dict):
    def from_env(self, variable_name):
        rv = os.environ.get(variable_name)
        if not rv:
            return False
        self.from_pyfile(rv)
        return True

    def from_pyfile(self, filename):
        filename = os.path.join(filename)
        d = imp.new_module('config')
        d.__file__ = filename
        execfile(filename, d.__dict__)
        self.from_object(d)
        return True

    def from_object(self, obj):
        for key in dir(obj):
            if key.isupper():
                self[key] = getattr(obj, key)
