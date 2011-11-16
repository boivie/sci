#!/usr/bin/env python
"""
    sci.ss
    ~~~~~~

    Storage Server

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
from optparse import OptionParser
import web, json, os

urls = (
    '/f/([0-9a-f]+)/(.+)',     'Transfer',
    '/list/([0-9a-f]+).json',  'ListSession')

web.config.debug = False
app = web.application(urls, globals())


def jsonify(**kwargs):
    web.header('Content-Type', 'application/json')
    return json.dumps(kwargs)


def abort(status, data):
    print("> %s" % data)
    raise web.webapi.HTTPError(status = status, data = data)


def get_spath(sid):
    spath = os.path.join(web.config._path, "sessions", sid)
    return spath


def get_fpath(sid, filename):
    fpath = os.path.join(get_spath(sid), filename)
    return fpath


def rglob(directory):
    matches = []
    for root, dirnames, filenames in os.walk(directory):
        for filename in filenames:
            fname = os.path.join(root, filename)
            fname = os.path.relpath(fname, directory)
            matches.append(fname)
    return matches


class ListSession:
    def GET(self, sid):
        spath = get_spath(sid)
        matches = rglob(spath)
        return jsonify(files = matches)


class Transfer:
    def PUT(self, sid, filename):
        if ".." in filename:
            abort(403, "Not Allowed")
        fpath = get_fpath(sid, filename)
        try:
            os.makedirs(os.path.dirname(fpath))
        except OSError:
            pass
        try:
            remaining = int(web.ctx.env.get('CONTENT_LENGTH'))
        except ValueError:
            abort(500, "Invalid content length")

        src = web.ctx.env['wsgi.input']
        with open(fpath, "w") as dst:
            while True:
                this_len = min(remaining, 1024 * 1024)
                if this_len == 0:
                    break
                part = src.read(this_len)
                if len(part) != this_len:
                    abort(500, "Failed to read data")
                dst.write(part)
                remaining -= this_len

        if ".." in filename:
            abort(403, "Not Allowed")
        return jsonify(status = "ok")

    def GET(self, sid, filename):
        try:
            with open(get_fpath(sid, filename), "rb") as src:
                while True:
                    data = src.read(100 * 1024)
                    if not data:
                        break
                    yield data
        except IOError:
            abort(404, "Not Found")


if __name__ == "__main__":
    parser = OptionParser()
    parser.add_option("-p", "--port", dest = "port", default = 6698,
                      help = "port to use")
    parser.add_option("--path", dest = "path", default = ".",
                      help = "path to use")

    (opts, args) = parser.parse_args()
    web.config._path = os.path.realpath(opts.path)

    web.httpserver.runsimple(app.wsgifunc(), ("0.0.0.0", int(opts.port)))
