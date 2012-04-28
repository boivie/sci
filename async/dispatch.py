import json
from sci.http_client import HttpClient
from jobserver.build import set_session_to_agent


def do_dispatch(db, agent_id, agent_info, session_id):
    agent_url = "http://%s:%s" % (agent_info["ip"], agent_info["port"])
    print("DISPATCH TO AGENT, URL: '%s'" % agent_url)

    set_session_to_agent(db, session_id, agent_id)
    input = dict(session_id = session_id)
    client = HttpClient(agent_url)
    client.call('/dispatch', input = json.dumps(input))
