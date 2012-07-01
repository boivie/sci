import logging
import signal
import time

import redis

__version__ = "0.1"
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)


def now():
    return time.time()


class Worker(object):
    def __init__(self, host, port=6379, db=0):
        self.db = redis.StrictRedis(host, port, db)
        self.last_ts = now()
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
        #signal.signal(signal.SIGUSR1, self.kill_child)

    def schedule_shutdown(self, signum, frame):
        logger.info("Shutdown scheduled")
        self._shutdown = True

    def work(self):
        while not self._shutdown:
            self.db.delete("timers_wakeup")
            first = self.db.zrangebyscore("timers", "-inf", "+inf",
                                          start=0, num=1, withscores=True)
            if first:
                timer, timeout = first[0]
                logger.debug("First in line = %s, %s" % (timer, timeout))
            else:
                timer, timeout = "none", now() + 1000
                logger.debug("No timers pending.")
            if timeout <= now():
                self.trigger(timer)
                self.reschedule(timer)
            else:
                self.sleep(timeout)

    def sleep(self, timeout):
        ts = now()
        next_ts = int(timeout - ts)
        s = "Idle for %d seconds, next in %d" % (ts - self.last_ts, next_ts)
        logger.debug(s)
        self.status(s)
        self.db.blpop("timers_wakeup", timeout=1)

    def trigger(self, timer):
        logger.info("Triggering %s" % timer)
        self.last_ts = now()

    def reschedule(self, timer):
        logger.debug("Rescheduling %s" % timer)
        self.db.zadd("timers", now() + 10, timer)

try:
    from setproctitle import setproctitle
    setproctitle  # workaround https://github.com/kevinw/pyflakes/issues/13
except ImportError:
    def setproctitle(name):
        pass

if __name__ == '__main__':
    Worker('localhost', 6379).run()
