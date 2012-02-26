import redis

pool = redis.ConnectionPool(host='localhost', port=6379, db=0)


def conn():
    r = redis.StrictRedis(connection_pool=pool)
    return r
