#!/usr/bin/env python
"""
    sci.ss
    ~~~~~~

    Storage Server

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""
import os

from flask import Flask, jsonify, abort, request, send_file, url_for

app = Flask(__name__)


def get_spath(build_id):
    return os.path.join(app.config['SS_PATH'], 'ss-files',
                        build_id[1:3], build_id[3:5], build_id[5:])


def get_fpath(build_id, filename):
    fpath = os.path.join(get_spath(build_id), filename)
    return fpath


def get_url(build_id, filename):
    return url_for('.get_file', build_id=build_id, filename=filename,
                   _external=True)


def rglob(directory):
    matches = []
    for root, dirnames, filenames in os.walk(directory):
        for filename in filenames:
            fname = os.path.join(root, filename)
            fname = os.path.relpath(fname, directory)
            matches.append(fname)
    return matches


@app.route('/list/<build_id>.json', methods=['GET'])
def list_session(build_id):
    spath = get_spath(build_id)
    matches = []
    for fname in rglob(spath):
        matches.append({'filename': fname,
                        'url': get_url(build_id, fname)})
    return jsonify(files=matches)


@app.route('/f/<build_id>/<filename>', methods=['PUT'])
def put_file(build_id, filename):
    if '..' in filename:
        abort(403)
    fpath = get_fpath(build_id, filename)
    try:
        os.makedirs(os.path.dirname(fpath))
    except OSError:
        pass
    try:
        remaining = int(request.headers.get('CONTENT_LENGTH'))
    except ValueError:
        abort(500)

    src = request.stream
    with open(fpath, 'w') as dst:
        while True:
            this_len = min(remaining, 1024 * 1024)
            if this_len == 0:
                break
            part = src.read(this_len)
            if len(part) != this_len:
                abort(500)
            dst.write(part)
            remaining -= this_len

    if '..' in filename:
        abort(403)

    return jsonify(status="ok", url=get_url(build_id, filename))


@app.route('/f/<build_id>/<filename>', methods=['GET'])
def get_file(build_id, filename):
    if '..' in filename or filename.startswith('/'):
        abort(404)
    filename = get_fpath(build_id, filename)
    if not os.path.exists(filename):
        abort(404)
    return send_file(filename)
