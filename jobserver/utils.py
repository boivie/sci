import re, time

re_sha1 = re.compile('^([0-9a-f]{40})$')


def is_sha1(ref):
    return re_sha1.match(ref)


def get_ts():
    return int(time.time())


def chunks(l, n):
    """ Yield successive n-sized chunks from l.
    """
    for i in xrange(0, len(l), n):
        yield l[i:i + n]
