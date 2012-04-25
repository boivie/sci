import json

from flask import Blueprint, jsonify, request

from jobserver.db import conn
from jobserver.slog import add_slog

app = Blueprint('slog', __name__)


@app.route('/<build_id>-<session_no>', methods=['POST'])
def add_log(build_id, session_no):
    data = json.dumps(request.json) if request.json else request.data
    add_slog(conn(), '%s-%s' % (build_id, session_no), data)
    return jsonify()
