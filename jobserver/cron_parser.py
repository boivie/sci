from datetime import datetime
from datetime import timedelta
import re

T_UNKNOWN, T_EOF, T_EVERY, T_DAY, T_DAILY, T_AT, \
    T_WORK, T_WEEKEND, T_COMMA, T_AND = range(10)


class CronEntry(object):
    def __init__(self, **kwargs):
        self.day_of_week = kwargs.get('day_of_week', [])
        self.time = kwargs.get('time', [])

    def next(self, now = None):
        # TODO: Timezone support
        now = now or datetime.now()
        now_week_day = now.weekday()
        this_wd_offsets = sorted([(d - now_week_day) % 7 for d in self.day_of_week])
        # 'today' can also mean 'one week from now' if we just missed the deadline
        if this_wd_offsets[0] == 0:
            this_wd_offsets += [7]
        for day_offset in this_wd_offsets:
            this_day = now + timedelta(day_offset)
            for time in self.time:
                hour, minute = time.split(":")
                then = datetime(this_day.year, this_day.month, this_day.day,
                                int(hour), int(minute))
                if then >= now:
                    return then

    def serialize(self):
        return dict(day_of_week = self.day_of_week,
                    time = self.time)

    def __str__(self):
        return str(self.serialize())

    def __eq__(self, other):
        return self.__dict__ == other.__dict__


class Lexer(object):
    def __init__(self, s):
        self.tokens = [t.strip().lower() for t in re.split('(\W+)', s) if t.strip()]
        self.i = 0

    def next(self, expect = None):
        if self.i == len(self.tokens):
            t = T_EOF
        else:
            t = self.tokens[self.i]
            self.i += 1
            try:
                t = {'every': T_EVERY,
                     'day': T_DAY,
                     'daily': T_DAILY,
                     'at': T_AT,
                     'work': T_WORK,
                     'weekend': T_WEEKEND,
                     ',': T_COMMA,
                     'and': T_AND}[t]
            except KeyError:
                pass
        if expect is not None and t != expect:
            raise ValueError("Expected %s, got %s" % (expect, t))
        return t


class CronParser(object):

    @classmethod
    def parse_date(cls, l, day_of_week):
        times = []
        p = l.next()
        while True:
            if p == T_EOF:
                break
            hours = int(p)
            l.next(":")
            p = l.next()
            minutes = int(p)
            times.append("%02d:%02d" % (hours, minutes))
            p = l.next()
            if p == T_COMMA or p == T_AND:
                p = l.next()
                continue
            elif p == T_EOF:
                break
            raise ValueError("Unexpected token: %s" % p)
        return CronEntry(day_of_week=day_of_week, time=times)

    @classmethod
    def parse_daily(cls, l, day_of_week = '*'):
        t = l.next()
        if t == T_EOF:
            return CronEntry(day_of_week=day_of_week, time=["00:00"])
        elif t == T_AT:
            return cls.parse_date(l, day_of_week)
        raise ValueError("expected 'at'")

    @classmethod
    def parse_day_of_week(cls, l):
        day_of_week = [-1, -1, -1, -1, -1, -1, -1]
        t = l.next()
        if t == T_DAY:
            return cls.parse_daily(l, range(7))
        while True:
            if t == T_WEEKEND:
                day_of_week = day_of_week[0:5] + [5, 6]
            elif t == T_WORK:
                l.next(T_DAY)
                day_of_week = [0, 1, 2, 3, 4] + day_of_week[6:7]
            elif t == 'monday':
                day_of_week[0] = 0
            elif t == 'tuesday':
                day_of_week[1] = 1
            elif t == 'wednesday':
                day_of_week[2] = 2
            elif t == 'thursday':
                day_of_week[3] = 3
            elif t == 'friday':
                day_of_week[4] = 4
            elif t == 'saturday':
                day_of_week[5] = 5
            elif t == 'sunday':
                day_of_week[6] = 6
            t = l.next()
            if t == T_AND:
                t = l.next()
                continue
            elif t == T_COMMA:
                t = l.next()
                continue
            elif t == T_EOF:
                day_of_week = filter(lambda x: x >= 0, day_of_week)
                return cls.parse_daily(l, day_of_week)
            elif t == T_AT:
                day_of_week = filter(lambda x: x >= 0, day_of_week)
                return cls.parse_date(l, day_of_week)
            else:
                raise ValueError("Error while parsing day of week")

    @classmethod
    def parse(cls, s):
        l = Lexer(s)
        t = l.next()
        if t == T_EVERY:
            return cls.parse_day_of_week(l)
        if t == T_DAILY:
            return cls.parse_daily(l, day_of_week=range(7))
        raise ValueError("Invalid cron string")


if __name__ == "__main__":
    c = CronParser.parse("every monday, wednesday and friday at 09:00, 10:00, 14:00 and 16:00")
    d = CronEntry(day_of_week=[0, 2, 4],
                  time=["09:00", "10:00", "14:00", "16:00"])
    assert(c == d)

    c = CronParser.parse("daily")
    d = CronEntry(day_of_week=[0, 1, 2, 3, 4, 5, 6], time=["00:00"])
    assert(c == d)

    c = CronParser.parse("every monday, wednesday and friday")
    assert(c == CronEntry(day_of_week=[0, 2, 4], time=["00:00"]))

    c = CronParser.parse("every monday, wednesday and friday at 09:00, 10:00, 14:00 and 16:00")
    # Same day
    assert(c.next(datetime(2013, 02, 27, 8, 25)) == datetime(2013, 02, 27, 9, 0))
    assert(c.next(datetime(2013, 02, 27, 9, 0)) == datetime(2013, 02, 27, 9, 0))
    assert(c.next(datetime(2013, 02, 27, 9, 0, 1)) == datetime(2013, 02, 27, 10, 0))
    assert(c.next(datetime(2013, 02, 27, 10, 25)) == datetime(2013, 02, 27, 14, 0))
    assert(c.next(datetime(2013, 02, 27, 15, 59, 59)) == datetime(2013, 02, 27, 16, 0))

    # Overwrap to next day
    assert(c.next(datetime(2013, 02, 27, 17, 14)) == datetime(2013, 03, 01, 9, 0))

    # One week from now
    assert(c.next(datetime(2013, 03, 06, 8, 25)) == datetime(2013, 03, 06, 9, 0))
    assert(c.next(datetime(2013, 03, 06, 9, 0, 1)) == datetime(2013, 03, 06, 10, 0))

    c = CronParser.parse("every wednesday at 09:00")
    # Missed by one minute
    assert(c.next(datetime(2013, 02, 27, 9, 0, 1)) == datetime(2013, 03, 06, 9, 0))

    # Missed by one day
    assert(c.next(datetime(2013, 02, 28, 9, 0, 0)) == datetime(2013, 03, 06, 9, 0))
