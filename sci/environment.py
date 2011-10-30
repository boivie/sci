"""
    sci.environment
    ~~~~~~~~~~~~~~~

    Environment Handling

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""


class EnvVar(object):
    def __init__(self, env, name):
        self.env = env
        self.name = name

    def set(self, value):
        self.env[self.name] = value

    def __call__(self):
        return self.env.get(self.name)


class Environment(dict):
    def __init__(self):
        pass

    def __call__(self, name):
        obj = EnvVar(self, name)
        return obj
