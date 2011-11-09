"""
    sci.session
    ~~~~~~~

    SCI Session

    Every job (and sub-job) is running in a session, which
    provides the directory structure needed for gathering
    log files and more.

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
import time, os, json, hashlib, random


def random_bytes(size):
    return "".join(chr(random.randrange(0, 256)) for i in xrange(size))


class Session(object):
    root_path = "."

    def __init__(self, id = None):
        self.id = id if id else hashlib.sha1(random_bytes(20)).hexdigest()
        self.path = self.__path(self.id)
        self.logfile = os.path.join(self.path, "output.log")
        self.workspace = os.path.join(self.path, "workspace")
        self.state = "created"
        self.created = time.time()
        self.ended = 0
        self.return_code = None
        self.return_value = None

    def save(self):
        with open(os.path.join(self.__path(self.id), "config.json"), "w") as f:
            d = self.__dict__
            f.write(json.dumps(d))

    @classmethod
    def create(cls):
        s = Session()
        os.makedirs(s.workspace)
        s.save()
        return s

    @classmethod
    def load(cls, id):
        with open(os.path.join(cls.__path(id), "config.json"), "r") as f:
            d = json.loads(f.read())
            s = Session()
            for key in d:
                setattr(s, key, d[key])
            return s

    @classmethod
    def __path(cls, sid):
        return os.path.join(cls.root_path, "sessions", sid)

    @classmethod
    def set_root_path(cls, path):
        cls.root_path = path