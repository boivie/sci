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

urls = (
    '/info/([0-9a-f]+).json', 'GetSessionInfo',
    '/start/(.+).json',       'StartJob',
    '/log/([0-9a-f]+).txt',   'GetLog',
    '/package/(.+)',          'Package',
    '/status.json',           'GetStatus')

EXPIRY_TTL = 60

web.config.debug = False
app = web.application(urls, globals())


class Settings(object):
    def __init__(self):
        self.job = None
        self.last_status = 0

settings = Settings()


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
            i = 0
            while True:
                if settings.job is None:
                    break
                i += 1
                if i % 10 == 0:
                    yield "\n"
                time.sleep(0.1)

        session = Session.load(sid)
        yield json.dumps({"state": session.state,
                          "return_value": session.return_value})


class StartJob:
    def POST(self, job_token):
        if settings.job:
            abort(412, "already running")
        n = LocalNode()
        web.config.job_no = int(job_token)
        settings.job = n.run_remote(None, web.data(), web.config._path)
        return jsonify(status = "started",
                       id = settings.job.session_id)


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


class GetStatus:
    def GET(self):
        if settings.job:
            return jsonify(status = "running")
        else:
            return jsonify(status = "idle")


class Package:
    def PUT(self, filename):
        destination = os.path.join(web.config._package_path, filename)
        if os.path.exists(destination):
            # Don't update it. Just skip it.
            return
        with open(destination, "w") as f:
            f.write(web.data())
        print("Updated %s" % destination)


def send_status(status):
    client = HttpClient("http://127.0.0.1:6699")

    status_str = {STATUS_AVAILABLE: "available",
                  STATUS_BUSY: "busy"}[status]
    print("%s checking in (%s)" % (web.config.token, status_str))
    client.call("/checkin/%s/%s/%d.json" % (web.config.token, status_str,
                                            web.config.job_no),
                method = "POST")

STATUS_AVAILABLE, STATUS_BUSY = range(2)


def get_status():
    if settings.job:
        if settings.job.poll():
            if settings.job.return_code != 0:
                print("Job CRASHED")
                # We never do that. It must have crashed - clear the session
                session = Session.load(settings.job.session_id)
                session.return_code = settings.job.return_code
                session.state = "finished"
                session.save()
            else:
                print("Job terminated")
            settings.job = None

    if settings.job:
        return STATUS_BUSY
    return STATUS_AVAILABLE


def ttl_expired():
    if settings.last_status + EXPIRY_TTL < int(time.time()):
        return True


class StatusThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.kill_received = False

    def run(self):
        # Wait a few seconds before staring - to let things settle
        time.sleep(3)
        reported_status = STATUS_BUSY
        while not self.kill_received:
            current_status = get_status()
            if current_status != reported_status or ttl_expired():
                send_status(current_status)
                reported_status = current_status
                settings.last_status = int(time.time())
            time.sleep(1)


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
    web.config._package_path = os.path.join(web.config._path, "packages")
    if not os.path.exists(web.config._package_path):
        os.makedirs(web.config._package_path)

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
    ret = client.call("/register/%s.json" % web.config.node_id,
                      input = json.dumps({"port": web.config.port,
                                          "labels": ["macos"]}))
    print("Got token %s, job_no %s" % (ret["token"], ret["job_no"]))
    web.config.token = ret["token"]
    web.config.job_no = ret["job_no"]

    print("%s: Running from %s, listening to %d" % (web.config.node_id, web.config._path, web.config.port))

    t = StatusThread()
    t.start()
    web.httpserver.runsimple(app.wsgifunc(), ("0.0.0.0", int(opts.port)))
    t.kill_received = True
