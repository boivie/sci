import json

from db import KEY_TIMERS_MAX, KEY_TIMERS, KEY_TIMER


def allocate(db, count=1):
    new_max = db.incr(KEY_TIMERS_MAX, count)
    new_timers = range(new_max - count + 1, new_max + 1)
    return new_timers


def add(pipe, timer_id, cron_entry, intent_json, description=''):
    d = {'intent': intent_json,
         'description': description,
         'schedule': json.dumps(cron_entry.serialize())}
    pipe.hmset(KEY_TIMER % timer_id, d)
    pipe.zadd(KEY_TIMERS, 0, timer_id)


def kill(pipe, timer_id):
    pipe.zrem(KEY_TIMERS, timer_id)
    pipe.delete(KEY_TIMER % timer_id)
