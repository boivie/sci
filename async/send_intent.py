

class SendIntent(object):
    queue = 'queue'

    @staticmethod
    def perform(intent):
        import json
        import logging
        from sci.http_client import HttpClient
        i = json.loads(intent)
        logging.debug("Processing %s intent: %s" % (i['type'], i['action']))
        extra = i.get('extra', {})

        # explicit 'build'
        if i['type'] == 'explicit' and i['action'] == 'build':
            jobserver_url = "http://localhost:6697"
            d = {'parameters': extra.get('parameters', {}),
                 'description': extra.get('description') or "Started from intent"}
            js = HttpClient(jobserver_url)
            r = js.call('/build/start/%s' % extra['job'], input = d)
            logging.info("Intent triggered build %s" % r['build_id'])
