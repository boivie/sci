"""
    sci.job
    ~~~~~~~

    Simple Continuous Integration

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
from optparse import OptionParser
import re, os, socket, time, sys, logging, types, subprocess, shlex
from datetime import datetime
from .config import Config
from .environment import Environment
from .params import Parameters, ParameterError
from .node import LocalNode, RemoteNode
from .artifacts import Artifacts
from .session import Session
from .package import Package
from .http_client import HttpClient
from .utils import random_sha1


re_var = re.compile("{{(.*?)}}")


class JobException(Exception):
    pass


class JobLocation(object):
    def __init__(self, package, filename):
        self.package = package
        self.filename = filename


class Step(object):
    def __init__(self, job, name, fun, **kwargs):
        self.job = job
        self.name = name
        self.fun = fun
        self.detached_jobs = []

    def __call__(self, *args, **kwargs):
        self.job._current_step = self
        self.job._print_banner("Step: '%s'" % self.name)
        ret = self.fun(*args, **kwargs)
        # Wait for any unfinished detached jobs
        for job in self.detached_jobs:
            job.join()
            self.job._print_banner("%s finished" % job.session_id)
        self.detached_jobs = []
        return ret

    def async(self, *args, **kwargs):
        node = self.job._allocate_node()
        rjob = node.run(self.job, self.fun, args, kwargs)
        self.job._current_step.detached_jobs.append(rjob)
        self.job._print_banner("%s @ %s" % (self.name, rjob.session_id))
        return rjob


class Job(object):
    def __init__(self, import_name, debug = False):
        self._import_name = import_name
        # The session is known when running - not this early
        self._session = None
        self.steps = []
        self._mainfn = None
        self._description = ""
        self.env = self._create_environment()
        self.id = None
        self._params = Parameters(self.env)
        self.artifacts = Artifacts(self, "http://localhost:6698")
        self.debug = debug
        self._master_url = os.environ.get("SCI_MASTER_URL")
        self._job_key = os.environ.get("SCI_JOB_KEY")
        self._location = None
        self._current_step = None

    def _allocate_node(self):
        if self._master_url is None:
            # Can not allocate a node - use local node
            return LocalNode()
        else:
            # Allocate one using the ahq
            client = HttpClient(self._master_url)
            result = client.call("/allocate/any.json", method = "POST")
            if result["status"] != "ok":
                raise Exception("Failed to allocate slave")
            logging.debug("Allocated %s (%s:%s)" % (result["agent"], result["ip"], result["port"]))
            return RemoteNode("http://%s:%s" % (result["ip"], result["port"]))

    def set_description(self, description):
        self._description = self.format(description)

    def get_description(self):
        return self._description

    description = property(get_description, set_description)

    def set_session(self, session):
        if self._session:
            raise JobException("The session can only be set once")
        self._session = session

    def get_session(self):
        return self._session

    session = property(get_session, set_session)

    def set_location(self, location):
        if self._location:
            raise JobException("The location can only be set once")
        self._location = location

    def get_location(self):
        return self._location

    location = property(get_location, set_location)

    def parameter(self, name, description = "", default = None,
                  **kwargs):
        param = self._params.declare(name, description = description,
                                     default = default, **kwargs)
        self.env.define(name, description, source = "parameter", final = True)
        return param

    def _create_environment(self):
        env = Environment()

        hostname = socket.gethostname()
        if hostname.endswith(".local"):
            hostname = hostname[:-len(".local")]
        env.define("SCI_HOSTNAME", "Host Name", read_only = True,
                   value = hostname, source = "initial environment")

        now = datetime.now()
        env.define("SCI_DATETIME", "The current date and time",
                   read_only = True, source = "initial environment",
                   value = now.strftime("%Y-%m-%d_%H-%M-%S"))
        return env

    ### Decorators ###

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
            self._mainfn = f
            return f
        return decorator

    def _timestr(self):
        delta = int(time.time() - self.start_time)
        if delta > 59:
            return "%dm%d" % (delta / 60, delta % 60)
        return "%d" % delta

    def _print_banner(self, text, dash = "-"):
        prefix = "[+%s]" % self._timestr()
        dash_left = (80 - len(text) - 4 - len(prefix)) / 2
        dash_right = 80 - len(text) - 4 - len(prefix) - dash_left
        print("%s%s[ %s ]%s" % (prefix, dash * dash_left,
                                 text, dash * dash_right))

    def _parse_arguments(self):
        # Parse parameters
        parser = OptionParser()
        parser.add_option("-c", "--config", dest = "config",
                          help = "configuration file to use")
        parser.add_option("--list-parameters", dest = "list_parameters",
                          action = "store_true",
                          help = "List job parameters and quit")
        (opts, args) = parser.parse_args()
        if opts.config:
            self.env.merge(Config.from_pyfile(opts.config))

        if opts.list_parameters:
            self._params.print_help()
            sys.exit(2)
        # Parse parameters specified as args:
        for arg in args:
            if "=" in arg:
                k, v = arg.split("=", 2)
                self.env[k] = v
        return opts, args

    def _start(self, session, entrypoint, params, args, kwargs, env, flags):
        assert(session)
        self.session = session
        if env is None:  # The root of all jobs
            self.id = session.id
            self.env["SCI_JOB_ID"] = self.id
        else:
            self.id = env["SCI_JOB_ID"]

        if flags.get("manually-started", False):
            opts, _ = self._parse_arguments()
        # Must set time first. It's used when printing
        self.start_time = time.time()
        self._print_banner("Preparing Job", dash = "=")

        # Read global config file
        config = Config.from_env("SCI_CONFIG")
        if config:
            self.env.merge(config)
            print("Loaded configuration from %s" % os.environ["SCI_CONFIG"])

        # Merge environments
        if env:
            self.env.merge(env)

        # Set parameters
        for k in params:
            self.env[k] = params[k]

        if flags.get("main-job", False):
            try:
                self._params.evaluate()
            except ParameterError as e:
                print("error: %s " % e)
                print("")
                print("Run with --list-parameters to list them.")
                sys.exit(2)

        print("Session ID: %s" % self.session.id)
        print("Location %s/%s" % (self.location.package,
                                  self.location.filename))
        self.env.print_values()

        self._print_banner("Starting Job", dash = "=")
        ret = entrypoint(*args, **kwargs)
        self._print_banner("Job Finished", dash = "=")
        return ret

    def start(self, params = {}):
        """Start a job manually (for testing)

           This method is only used when running a job manually by
           invoking the job's script from the command line."""
        # Create a package, so that we mimic how real jobs work
        mfilename = sys.modules[self._import_name].__file__
        this_dir = os.path.dirname(os.path.realpath(mfilename))
        output_dir = os.path.join(os.path.dirname(__file__), "packages")
        package = Package.create(this_dir, output_dir)

        session = Session.create()
        flags = {"main-job": True, "manually-started": True}
        return package.run(session, os.path.basename(mfilename),
                           params = params, flags = flags)

    def run(self, cmd, **kwargs):
        cmd = self.format(cmd, **kwargs)
        devnull = open("/dev/null", "r")
        p = subprocess.Popen(cmd,
                             shell = True,
                             stdin = devnull, stdout = sys.stdout,
                             stderr = sys.stderr,
                             cwd = self.session.workspace)
        p.communicate()
        if p.returncode != 0:
            self.error("Command failed")

    def _format(self, tmpl, **kwargs):
        while True:
            m = re_var.search(tmpl)
            if not m:
                break
            name = m.groups()[0]
            value = self.var(name, **kwargs)
            if not value:
                self.error("Failed to replace template variable %s" % name)
            tmpl = tmpl.replace("{{%s}}" % name, str(value))
        return tmpl

    def format(self, tmpl, **kwargs):
        if isinstance(tmpl, basestring):
            return self._format(tmpl, **kwargs)
        elif isinstance(tmpl, types.ListType):
            return [self._format(t, **kwargs) for t in tmpl]
        else:
            raise TypeError("Invalid type for format")

    def var(self, _key, **kwargs):
        value = kwargs.get(_key)
        if not value:
            value = self.env.get(_key)
        return value

    def error(self, what):
        raise JobException(what)
