from datetime import datetime
import json
import logging
import signal
import time

from pyres import ResQ
import redis

from jobserver.cron_parser import CronEntry

__version__ = "0.1"
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)


def now():
    return time.time()


class Worker(object):
    def __init__(self, host, port=6379, db=0):
        self.db = redis.StrictRedis(host, port, db)
        self._shutdown = False

    def status(self, s):
        setproctitle('sci-crond-%s: %s' % (__version__, s))

    def run(self):
        self.status("Starting")
        self.register_signal_handlers()
        self.work()

    def register_signal_handlers(self):
        signal.signal(signal.SIGTERM, self.schedule_shutdown)
        signal.signal(signal.SIGINT, self.schedule_shutdown)
        signal.signal(signal.SIGQUIT, self.schedule_shutdown)

    def schedule_shutdown(self, signum, frame):
        logger.info("Shutdown scheduled")
        self._shutdown = True

    def work(self):
        while not self._shutdown:
            self.db.delete("timers_wakeup")
            ts = now()
            first = self.db.zrangebyscore("timers", "-inf", "+inf",
                                          start=0, num=1, withscores=True)
            if first:
                timer, timeout = first[0]
                logger.debug("First in line = %s, %s (%s seconds from now)" %
                             (timer, timeout, timeout - ts))
                if timeout == 0:
                    self.reschedule(timer, ts)
                    continue
            else:
                timer, timeout = "none", ts + 1000
                logger.debug("No timers pending.")

            if timeout <= ts:
                self.trigger(timer)
                self.reschedule(timer, ts)
            else:
                self.sleep(timeout, ts)

    def sleep(self, timeout, ts):
        next_ts = int(timeout - ts)
        s = "Next timeout in %d seconds" % next_ts
        self.status(s)
        self.db.blpop("timers_wakeup", timeout=1)

    def trigger(self, timer):
        intent_json = self.db.hget('timer:%s' % timer, 'intent')
        if not intent_json:
            logging.warning("Triggering timer %s, but found no intent" % timer)
            return

        from async.send_intent import SendIntent
        r = ResQ()
        r.enqueue(SendIntent, intent_json)

    def reschedule(self, timer, ts):
        schedule = self.db.hget('timer:%s' % timer, 'schedule')
        if schedule:
            ce = CronEntry(**json.loads(schedule))
            next_dt = ce.next(datetime.fromtimestamp(ts))
            next_ts = time.mktime(next_dt.timetuple())
            self.db.zadd("timers", next_ts, timer)
        else:
            logging.error("Non-repeating timers are not handled!")
            # Need to disable that timer.
            self.db.zrem("timers", timer)


try:
    from setproctitle import setproctitle
    setproctitle  # workaround https://github.com/kevinw/pyflakes/issues/13
except ImportError:
    def setproctitle(name):
        pass

if __name__ == '__main__':
    Worker('localhost', 6379).run()
