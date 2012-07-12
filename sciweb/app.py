from datetime import datetime

from flask import Flask, render_template
import json, logging, types
from recipes import app as recipes_app
from agents import app as agents_app
from builds import app as builds_app
from search import app as search_app
from sci.http_client import HttpClient

app = Flask(__name__)
app.register_blueprint(recipes_app, url_prefix='/recipes')
app.register_blueprint(agents_app, url_prefix='/agents')
app.register_blueprint(builds_app, url_prefix='/builds')
app.register_blueprint(search_app, url_prefix='/search')


def js():
    return HttpClient('http://' + app.config['JS_SERVER_NAME'])


@app.template_filter('json')
def to_json(obj):
    return json.dumps(obj)


@app.template_filter('short_id')
def short_id(s):
    if len(s) != 40:
        logging.debug("Warning: Not an id? %s" % s)
    return s[0:7]


@app.template_filter('format_dur')
def format_dur(dur):
    return "%02d:%02d:%02d" % (dur / 3600, (dur % 3600) / 60, dur % 60)


@app.template_filter('format_array')
def format_array(arr):
    return ", ".join(arr)


@app.template_filter('date_hm')
def date_hm(ts):
    dt = datetime.fromtimestamp(ts)
    return dt.strftime("%Y-%m-%d %H:%M")


@app.template_filter('pretty_dur')
def pretty_dur(dur):
    if dur < 1000:
        return "%d ms" % dur
    elif dur < (60 * 1000):
        return "%d s" % (dur / 1000)
    else:
        dur = int(dur / 1000)
        hours = int(dur / 3600)
        minutes = int((dur % 3600) / 60)
        seconds = dur % 60
        if hours == 0:
            return "%d:%d" % (minutes, seconds)
        else:
            return "%d:%d:%d" % (hours, minutes, seconds)


@app.template_filter('pretty_date')
def pretty_date(time=False):
    """
    Get a datetime object or a int() Epoch timestamp and return a
    pretty string like 'an hour ago', 'Yesterday', '3 months ago',
    'just now', etc
    """
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
        return "yesterday"
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
    recent = js().call("/build/recent/done")['recent']
    return render_template("index.html",
                           recent = recent)
