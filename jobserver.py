#!/usr/bin/env python
"""
    sci.jobserver
    ~~~~~~~~~~~~~

    Job Server

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
from optparse import OptionParser
import os

from dulwich.repo import Repo
import web

from jobserver.gitdb import get_gits
from jobserver.build_app import build_app
from jobserver.slog_app import slog_app
from jobserver.job_app import job_app
from jobserver.recipe_app import recipe_app
from jobserver.config_app import config_app

urls = (
    '/config', config_app,
    '/build',  build_app,
    '/slog',   slog_app,
    '/job',    job_app,
    '/recipe', recipe_app,
)

app = web.application(urls, globals())


if __name__ == "__main__":
    parser = OptionParser()
    parser.add_option("-g", "--debug",
                      action = "store_true", dest = "debug", default = False,
                      help = "debug mode - will allow all requests")
    parser.add_option("-p", "--port", dest = "port", default = 6697,
                      help = "port to use")
    parser.add_option("--path", dest = "path", default = ".",
                      help = "path to use")

    (opts, args) = parser.parse_args()

    web.config._path = opts.path
    for git_path in get_gits():
        if not os.path.exists(git_path):
            print("Creating initial repository: %s" % git_path)
            os.makedirs(git_path)
            Repo.init_bare(git_path)

    web.httpserver.runsimple(app.wsgifunc(), ("0.0.0.0", int(opts.port)))
