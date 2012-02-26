import web

from jobserver.db import conn
from jobserver.slog import add_slog

urls = (
    '/B([0-9a-f]{40})-([0-9]+)',  'AddLog',
)

slog_app = web.application(urls, locals())


class AddLog:
    def POST(self, build_id, session_no):
        add_slog(conn(), 'B%s-%s' % (build_id, session_no), web.data())
        return web.webapi.created()
