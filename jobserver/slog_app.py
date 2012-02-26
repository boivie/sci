import web

from jobserver.db import conn
from jobserver.webutils import abort, jsonify
from jobserver.slog import add_slog

urls = (
    '/B([0-9a-f]{40})/S([0-9a-f]{40})',  'AddLog',
)

slog_app = web.application(urls, locals())


class AddLog:
    def POST(self, build_id, session_id):
        if not add_slog(conn(), 'B' + build_id, 'S' + session_id, web.data()):
            abort(404, 'Invalid Build ID')
        return jsonify()
