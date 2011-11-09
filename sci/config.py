"""
    sci.config
    ~~~~~~~~~~

    Configuration Handling

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
import imp, os


class Config(dict):
    @classmethod
    def from_env(self, variable_name):
        rv = os.environ.get(variable_name)
        if not rv:
            return None
        return Config.from_pyfile(rv)

    @classmethod
    def from_pyfile(self, filename):
        filename = os.path.join(filename)
        d = imp.new_module('config')
        d.__file__ = filename
        execfile(filename, d.__dict__)
        return Config.from_object(d)

    @classmethod
    def from_object(self, obj):
        c = Config()
        for key in dir(obj):
            if key.isupper():
                c[key] = getattr(obj, key)
        return c
