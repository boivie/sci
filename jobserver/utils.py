import re, time

re_sha1 = re.compile('^([0-9a-f]{40})$')


def is_sha1(ref):
    return re_sha1.match(ref)


def get_ts():
    return int(time.time())
