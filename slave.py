#!/usr/bin/env python
"""
    sci.slave
    ~~~~~~~

    Slave Entrypoint

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
from optparse import OptionParser
import web, json, os, threading, subprocess
from sci.session import Session, time
from sci.http_client import HttpClient
from sci.utils import random_sha1
import ConfigParser
from Queue import Queue, Full, Empty

urls = (
    '/dispatch', 'StartJob',
)

EXPIRY_TTL = 60

web.config.debug = False
app = web.application(urls, globals())

requestq = Queue()
cv = threading.Condition()


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


class StartJob:
    def POST(self):
        if not put_item(web.data()):
            abort(412, "Busy")
        return jsonify(status = "started")


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


def send_available(dispatch_id = None, job_result = None):
    web.config.last_status = int(time.time())
    print("%s checking in (available)" % web.config.token)

    client = HttpClient("http://127.0.0.1:6699")
    result = client.call("/available/%s" % web.config.token,
                         input = json.dumps({'id': dispatch_id,
                                             'result': job_result}))
    return result.get('do')


def send_busy():
    web.config.last_status = int(time.time())
    print("%s checking in (busy)" % web.config.token)

    client = HttpClient("http://127.0.0.1:6699")
    client.call("/busy/%s" % web.config.token,
                method = 'POST')


def send_ping():
    web.config.last_status = int(time.time())
    print("%s pinging" % web.config.token)

    client = HttpClient("http://127.0.0.1:6699")
    client.call("/ping/%s" % web.config.token,
                method = "POST")


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


def get_item():
    with cv:
        while True:
            try:
                item = requestq.get_nowait()
                if item == None:
                    # Our 'busy' marker. Guess we are not as busy as we
                    # believe right now.
                    continue
                # Oh, it succeeded. Let's act 'busy'
                requestq.put(None)
                break
            except Empty:
                cv.wait()
    return item


def put_item(item):
    """Returns False if the ExcutionThread is working"""
    with cv:
        try:
            requestq.put_nowait(item)
            cv.notify()
            return True
        except Full:
            return False


def replace_item(item):
    # Assumes that the queue already has an item in it.
    with cv:
        requestq.get()
        requestq.put(item)
        cv.notify()


class ExecutionThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.kill_received = False

    def run(self):
        item = send_available()
        while not self.kill_received:
            if not item:
                item = get_item()

            session_id = json.loads(item)['session_id']
            session = Session.create(session_id)
            run_job = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                   "run_job.py")
            args = [run_job, session.id]
            stdout = open(session.logfile, "w")
            session.state = "running"
            session.save()
            proc = subprocess.Popen(args, stdin = subprocess.PIPE,
                                    stdout = stdout, stderr = subprocess.STDOUT,
                                    cwd = web.config._path)
            proc.stdin.write(item)
            proc.stdin.close()
            send_busy()
            return_code = proc.wait()
            session = Session.load(session.id)
            if return_code != 0:
                # We never do that. It must have crashed - clear the session
                print("Job CRASHED")
                session.return_code = return_code
                session.state = "finished"
                session.save()
            else:
                print("Job terminated")

            job_result = session.return_value
            item = send_available(session_id, job_result)


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

    web.config.port = int(opts.port)

    print("Registering at AHQ and getting token")
    client = HttpClient("http://127.0.0.1:6699")
    ret = client.call("/register",
                      input = json.dumps({"id": web.config.node_id,
                                          "port": web.config.port,
                                          "labels": ["macos"]}))
    print("Got token %s" % ret["token"])
    web.config.token = ret["token"]

    print("%s: Running from %s, listening to %d" % (web.config.node_id, web.config._path, web.config.port))

    status = StatusThread()
    execthread = ExecutionThread()
    status.start()
    execthread.start()
    web.httpserver.runsimple(app.wsgifunc(), ("0.0.0.0", int(opts.port)))
    status.kill_received = True
    execthread.kill_received = True
    put_item(None)
