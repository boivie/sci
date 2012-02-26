import web

from jobserver.db import conn
from jobserver.slog import add_slog

urls = (
    '/S([0-9a-f]{40})',  'AddLog',
)

slog_app = web.application(urls, locals())


class AddLog:
    def POST(self, session_id):
        session_id = 'S' + session_id
        add_slog(conn(), session_id, web.data())
        return web.webapi.created()
