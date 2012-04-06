import redis

pool = redis.ConnectionPool(host='localhost', port=6379, db=0)

KEY_LABEL = 'ahq:label:%s'
KEY_AGENT = 'agent:info:%s'
KEY_QUEUED_SESSIONS = 'sessionq'

KEY_ALL = 'agents:all'
KEY_AVAILABLE = 'agents:avail'

KEY_QUEUE = 'js:queue'
KEY_ALLOCATION = "ahq:alloc:%s"

# Agent has not checked in for a long time
AGENT_STATE_INACTIVE = "inactive"
# Agent is online and idle
AGENT_STATE_AVAIL = "available"
# A session has been dispatched to the agent
AGENT_STATE_PENDING = "pending"
# The agent has acknowledged the session and is now busy
AGENT_STATE_BUSY = "busy"


def conn():
    r = redis.StrictRedis(connection_pool=pool)
    return r
