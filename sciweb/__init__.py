from flask import Flask
import logging, types
from recipes import app as recipes_app
from agents import app as agents_app
from builds import app as builds_app

app = Flask(__name__)
app.register_blueprint(recipes_app, url_prefix='/recipes')
app.register_blueprint(agents_app, url_prefix='/agents')
app.register_blueprint(builds_app, url_prefix='/builds')

if app.debug:
    logging.basicConfig(level=logging.DEBUG)


@app.template_filter('short_id')
def short_id(s):
    if len(s) != 40:
        logging.debug("Warning: Not an id? %s" % s)
    return s[0:7]


@app.template_filter('pretty_date')
def pretty_date(time=False):
    """
    Get a datetime object or a int() Epoch timestamp and return a
    pretty string like 'an hour ago', 'Yesterday', '3 months ago',
    'just now', etc
    """
    from datetime import datetime
    now = datetime.now()
    if type(time) in types.StringTypes:
        time = int(time)
    if type(time) is int:
        if time == 0:
            return 'never'
        diff = now - datetime.fromtimestamp(time)
    elif isinstance(time, datetime):
        diff = now - time
    elif not time:
        diff = now - now
    second_diff = diff.seconds
    day_diff = diff.days

    if day_diff < 0:
        return ''

    if day_diff == 0:
        if second_diff < 10:
            return "just now"
        if second_diff < 60:
            return str(second_diff) + " seconds ago"
        if second_diff < 120:
            return  "a minute ago"
        if second_diff < 3600:
            return str(second_diff / 60) + " minutes ago"
        if second_diff < 7200:
            return "an hour ago"
        if second_diff < 86400:
            return str(second_diff / 3600) + " hours ago"
    if day_diff == 1:
        return "Yesterday"
    if day_diff < 7:
        return str(day_diff) + " days ago"
    if day_diff < 31:
        return str(day_diff / 7) + " weeks ago"
    if day_diff < 365:
        return str(day_diff / 30) + " months ago"
    return str(day_diff / 365) + " years ago"


@app.before_request
def before_request():
    pass


@app.after_request
def after_request(resp):
    return resp


@app.route("/", methods = ["GET"])
def index():
    return "Hello World"
