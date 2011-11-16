import urlparse, httplib, json, urllib


class HttpClient(object):
    def __init__(self, url):
        self.url = url

    def call(self, path, method = None, input = None, raw = False, **kwargs):
        with HttpRequest(self.url, path, method, input, **kwargs) as f:
            data = f.read()
            if raw:
                return data
            return json.loads(data)


class HttpRequest(object):
    def __init__(self, url, path, method = None, input = None, **kwargs):
        if not method:
            method = "POST" if input else "GET"
        headers = {"Accept": "application/json, text/plain, */*"}
        u = urlparse.urlparse(url + path)
        self.c = httplib.HTTPConnection(u.hostname, u.port)
        url = u.path
        if kwargs:
            url += "?" + urllib.urlencode(kwargs)
        self.c.request(method, url, input, headers)
        self.r = self.c.getresponse()
        if self.r.status != 200:
            raise Exception("Failed")

    def read(self, n = None):
        if n is None:
            return self.r.read()
        else:
            return self.r.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.c.close()
