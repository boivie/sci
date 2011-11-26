#!/usr/bin/env python
"""
    sci.slave
    ~~~~~~~

    Slave Entrypoint

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
from optparse import OptionParser
import web, json, sys, os, threading
from sci.session import Session, time
from sci.node import LocalNode
from sci.http_client import HttpClient
from sci.utils import random_sha1
import ConfigParser
from Queue import Queue

urls = (
    '/info/([0-9a-f]+).json', 'GetSessionInfo',
    '/start/(.+).json',       'StartJob',
    '/log/([0-9a-f]+).txt',   'GetLog')

EXPIRY_TTL = 60

web.config.debug = False
app = web.application(urls, globals())
jobqueue = Queue()
available = threading.Event()
available_lock = threading.RLock()


def get_config(path):
    c = ConfigParser.ConfigParser()
    c.read(os.path.join(path, "config.ini"))
    try:
        return {"node_id": c.get("sci", "node_id")}
    except ConfigParser.NoOptionError:
        return None
    except ConfigParser.NoSectionError:
        return None


def save_config(path, node_id):
    c = ConfigParser.ConfigParser()
    c.add_section('sci')
    c.set("sci", "node_id", node_id)
    with open(os.path.join(path, "config.ini"), "wb") as configfile:
        c.write(configfile)


def jsonify(**kwargs):
    web.header('Content-Type', 'application/json')
    return json.dumps(kwargs)


def abort(status, data):
    print("> %s" % data)
    raise web.webapi.HTTPError(status = status, data = data)


class GetSessionInfo:
    def GET(self, sid):
        web.header('Content-Type', 'application/json')
        session = Session.load(sid)
        if not session:
            abort(404, "session not found")

        args = web.input(block = '0')
        if args["block"] == '1':
            while not available.wait(10):
                yield "\n"

        session = Session.load(sid)
        yield json.dumps({"state": session.state,
                          "return_value": session.return_value})


class StartJob:
    def POST(self, job_token):
        with available_lock:
            if not available.is_set():
                abort(412, "Already running")
            available.clear()
        n = LocalNode()
        web.config.job_no = int(job_token)
        job = n.run_remote(None, web.data(), web.config._path)
        jobqueue.put(job)
        return jsonify(status = "started",
                       id = job.session_id)


class GetLog:
    def GET(self, sid):
        web.header('Content-type', 'text/plain')
        web.header('Transfer-Encoding', 'chunked')
        session = Session.load(sid)
        if not session:
            abort(404, "session not found")
        with open(session.logfile, "rb") as f:
            while True:
                data = f.read(4096)
                if not data:
                    break
                yield data


def send_status(status):
    client = HttpClient("http://127.0.0.1:6699")

    status_str = {STATUS_AVAILABLE: "available",
                  STATUS_BUSY: "busy"}[status]
    print("%s checking in (%s)" % (web.config.token, status_str))
    client.call("/%s/checkin/%s/%d.json" % (web.config.token, status_str,
                                            web.config.job_no),
                method = "POST")
    web.config.last_status = int(time.time())


def send_ping():
    client = HttpClient("http://127.0.0.1:6699")
    print("%s pinging" % web.config.token)
    client.call("/%s/ping.json" % web.config.token,
                method = "POST")
    web.config.last_status = int(time.time())


STATUS_AVAILABLE, STATUS_BUSY = range(2)


def ttl_expired():
    if web.config.last_status + EXPIRY_TTL < int(time.time()):
        return True


class StatusThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.kill_received = False

    def run(self):
        # Wait a few seconds before starting - there will be an initial
        # status sent from ExecutionThread.
        time.sleep(3)
        while not self.kill_received:
            if ttl_expired():
                send_ping()
            time.sleep(1)


class ExecutionThread(threading.Thread):
    def __init__(self, queue):
        threading.Thread.__init__(self)
        self.kill_received = False
        self.queue = queue

    def run(self):
        send_status(STATUS_AVAILABLE)
        while not self.kill_received:
            job = self.queue.get()
            if not job:
                continue
            assert(not available.is_set())
            send_status(STATUS_BUSY)
            job.join()
            if job.return_code != 0:
                print("Job CRASHED")
                # We never do that. It must have crashed - clear the session
                session = Session.load(job.session_id)
                session.return_code = job.return_code
                session.state = "finished"
                session.save()
            else:
                print("Job terminated")
            with available_lock:
                available.set()
            send_status(STATUS_AVAILABLE)


if __name__ == "__main__":
    parser = OptionParser()
    parser.add_option("-c", "--config", dest = "config",
                      help = "configuration file to use")
    parser.add_option("-g", "--debug",
                      action = "store_true", dest = "debug", default = False,
                      help = "debug mode - will allow all requests")
    parser.add_option("-p", "--port", dest = "port", default = 6700,
                      help = "port to use")
    parser.add_option("--path", dest = "path", default = ".",
                      help = "path to use")
    parser.add_option("-k", "--key", dest = "key",
                      help = "security key")

    (opts, args) = parser.parse_args()

    if opts.config:
        raise NotImplemented()
    if opts.key:
        web.config.key = opts.key
    if opts.path:
        if not os.path.exists(opts.path):
            os.makedirs(opts.path)
        web.config._path = os.path.realpath(opts.path)

    Session.set_root_path(web.config._path)

    config = get_config(web.config._path)
    if not config:
        web.config.node_id = random_sha1()
        save_config(web.config._path, web.config.node_id)
    else:
        web.config.node_id = config["node_id"]

    if not web.config.key:
        print >> sys.stderr, "Please specify a configuration file or a key"
        sys.exit(1)

    web.config.port = int(opts.port)

    print("Registering at AHQ and getting token")
    client = HttpClient("http://127.0.0.1:6699")
    ret = client.call("/A%s/register.json" % web.config.node_id,
                      input = json.dumps({"port": web.config.port,
                                          "labels": ["macos"]}))
    print("Got token %s, job_no %s" % (ret["token"], ret["job_no"]))
    web.config.token = ret["token"]
    web.config.job_no = ret["job_no"]

    print("%s: Running from %s, listening to %d" % (web.config.node_id, web.config._path, web.config.port))

    available.set()
    status = StatusThread()
    execthread = ExecutionThread(jobqueue)
    status.start()
    execthread.start()
    web.httpserver.runsimple(app.wsgifunc(), ("0.0.0.0", int(opts.port)))
    status.kill_received = True
    execthread.kill_received = True
    jobqueue.put(None)
