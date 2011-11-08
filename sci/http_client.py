import urlparse, httplib, json, urllib


class HttpClient(object):
    def __init__(self, url):
        self.url = url

    def call(self, path, method = None, input = None, **kwargs):
        if method is None:
            method = "POST" if input else "GET"
        headers = {"Accept": "application/json, text/plain, */*"}
        u = urlparse.urlparse(self.url + path)
        c = httplib.HTTPConnection(u.hostname, u.port)
        url = u.path
        if kwargs:
            url += "?" + urllib.urlencode(kwargs)
        c.request(method, url, input, headers)
        r = c.getresponse()
        if r.status != 200:
            raise Exception("Failed")
        data = r.read()
        c.close()
        return json.loads(data)
