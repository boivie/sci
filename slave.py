#!/usr/bin/env python
"""
    sci.slave
    ~~~~~~~

    Slave Entrypoint

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
from optparse import OptionParser
import web, json, sys, os
from sci.session import Session, time
from sci.node import LocalNode

urls = (
    '/info/([0-9a-f]+).json', 'GetSessionInfo',
    '/start.json',            'StartJob',
    '/log/([0-9a-f]+).txt',   'GetLog',
    '/status.json',           'GetStatus')

app = web.application(urls, globals())


class Settings(object):
    key = None
    path = "."
    job = None

settings = Settings()


def jsonify(**kwargs):
    web.header('Content-Type', 'application/json')
    return json.dumps(kwargs)


def before_request():
    if settings.job:
        retcode = settings.job.poll()
        if not retcode is None:
            print("Job terminated with return code %s" % retcode)
            if retcode != 0:
                # We never do that. It must have crashed - clear the session
                session = Session.load(settings.job.session_id)
                session.return_code = retcode
                session.state = "finished"
                session.save()
            settings.job = None


def abort(status, data):
    print("> %s" % data)
    raise web.webapi.HTTPError(status = status, data = data)


class GetSessionInfo:
    def GET(self, sid):
        before_request()
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
                before_request()

        session = Session.load(sid)
        yield json.dumps({"state": session.state})


class StartJob:
    def POST(self):
        before_request()
        if settings.job:
            abort(412, "already running")
        n = LocalNode("S0")
        settings.job = n.run_remote(web.data())
        return jsonify(status = "started",
                       id = settings.job.session_id)


class GetLog:
    def GET(self, sid):
        before_request()
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
        before_request()
        if settings.job:
            return jsonify(status = "running")
        else:
            return jsonify(status = "idle")

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
        settings.key = opts.key
    if opts.path:
        settings.path = opts.path
        Session.set_root_path(settings.path)
    settings.path = os.path.realpath(settings.path)
    print("Running from %s" % settings.path)

    if not settings.key:
        print >> sys.stderr, "Please specify a configuration file or a key"
        sys.exit(1)

    web.httpserver.runsimple(app.wsgifunc(), ("0.0.0.0", int(opts.port)))
