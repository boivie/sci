import redis

pool = redis.ConnectionPool(host='localhost', port=6379, db=0)

KEY_LABEL = 'ahq:label:%s'
KEY_AGENT = 'agent:info:%s'
KEY_DISPATCH_INFO = 'ahq:dispatch:info:%s'
KEY_QUEUE = 'ahq:dispatchq'

KEY_ALL = 'agents:all'
KEY_AVAILABLE = 'agents:avail'

KEY_QUEUE = 'js:queue'
KEY_ALLOCATION = "ahq:alloc:%s"

AGENT_STATE_INACTIVE = "inactive"
AGENT_STATE_AVAIL = "available"
AGENT_STATE_PENDING = "pending"
AGENT_STATE_BUSY = "busy"


def conn():
    r = redis.StrictRedis(connection_pool=pool)
    return r
