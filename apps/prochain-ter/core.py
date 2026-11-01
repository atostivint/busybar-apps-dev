"""Pure logic: merge real-time into the timetable, commute windows, leave-by, alerts.

No network, no clock of its own: everything takes `now` so it can be tested.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class Window:
    name: str
    days: frozenset  # Monday = 0
    start: int       # minutes after midnight, local time
    end: int
    direction: str   # "out" (home station -> Rennes) or "back" (Rennes -> home station)

    def active(self, now: datetime):
        m = now.hour * 60 + now.minute
        return now.weekday() in self.days and self.start <= m < self.end


def parse_hhmm(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def parse_days(s):
    names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    return frozenset(names.index(d.strip()[:3].lower()) for d in s.split(",") if d.strip())


def active_window(now, windows):
    for w in windows:
        if w.active(now):
            return w
    return None


def merge(scheduled, rt, origin, tz):
    """Scheduled trips + real-time feed -> departures with delay/cancellation."""
    out = []
    for t in scheduled:
        info = rt.get((t["number"], t["date"]))
        stop = info["stops"].get(origin) if info else None
        cancelled = bool(info and (info["canceled"] or (stop and stop["skipped"])))
        delay_s = 0
        if stop and stop["dep"]:
            delay_s = int(stop["dep"] - t["dep"].timestamp())
        elif stop and stop["delay"]:
            delay_s = stop["delay"]
        delay_min = round(delay_s / 60)
        out.append({**t, "cancelled": cancelled, "delay_min": delay_min, "live": info is not None,
                    "real_dep": t["dep"] + timedelta(seconds=delay_s),
                    "real_arr": t["arr"] + timedelta(seconds=delay_s)})
    return out


def leave_by(dep, buffer_min):
    return dep["real_dep"] - timedelta(minutes=buffer_min)


def pick(deps, now, buffer_min):
    """-> (target, backup, missed). First running train you can still catch, then the next one."""
    ok = [d for d in deps if not d["cancelled"] and leave_by(d, buffer_min) >= now]
    missed = [d for d in deps if not d["cancelled"] and d["real_dep"] > now > leave_by(d, buffer_min)]
    return (ok[0] if ok else None), (ok[1] if len(ok) > 1 else None), (missed[-1] if missed else None)


def minutes_until(when, now):
    return int((when - now).total_seconds() // 60)


THRESHOLDS = (15, 5, 0)  # minutes before leave-by


class Alerts:
    """Fire each threshold once per train; re-alert when a delay changes by >= 3 min or on cancel."""

    def __init__(self):
        self.fired = set()
        self.last = {}  # train key -> (delay_min, cancelled)

    def check(self, target, now, buffer_min, cancelled_seen=()):
        events = []
        for c in cancelled_seen:
            key = (c["number"], c["date"])
            if self.last.get(key, (0, False))[1] is False:
                self.last[key] = (c["delay_min"], True)
                events.append(("cancelled", c))
        if target is None:
            return events
        key = (target["number"], target["date"])
        prev = self.last.get(key)
        if prev is not None and abs(target["delay_min"] - prev[0]) >= 3:
            events.append(("delay", target))
            self.last[key] = (target["delay_min"], False)
        elif prev is None:
            self.last[key] = (target["delay_min"], False)
        left = minutes_until(leave_by(target, buffer_min), now)
        for th in sorted(THRESHOLDS):  # the tightest threshold already crossed wins
            if left <= th and (key, th) not in self.fired:
                for lower in THRESHOLDS:  # a late start must not replay the earlier chimes
                    if lower >= th:
                        self.fired.add((key, lower))
                events.append((f"t{th}", target))
                break
        return events
