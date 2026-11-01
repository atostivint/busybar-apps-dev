"""Pure logic: merge real-time into the timetable, commute windows, phases, alerts.

No network, no clock of its own: everything takes `now` so it can be tested.

For a train that leaves at D (real departure, delay included):
    go      = D - car_min        you must be in the car (drive + parking + walk)
    prepare = go - prep_min      time to start getting ready
Phases: wait (before prepare) -> prep (getting ready) -> go (leave now, GRACE_MIN of slack)
-> late (too late for this train, take the next one).
"""
import math
from dataclasses import dataclass
from datetime import datetime, timedelta

GRACE_MIN = 2  # minutes after `go` during which leaving can still work


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


def times(dep, prep_min, car_min):
    """-> (prepare_at, go_at) for a departure."""
    go = dep["real_dep"] - timedelta(minutes=car_min)
    return go - timedelta(minutes=prep_min), go


def minutes_until(when, now):
    """Whole minutes left, rounded up (4 min 10 s shows 5), never negative."""
    return max(0, math.ceil((when - now).total_seconds() / 60))


def phase(dep, now, prep_min, car_min):
    """-> ("wait" | "prep" | "go" | "late", minutes to the next milestone)."""
    prepare_at, go_at = times(dep, prep_min, car_min)
    if now < prepare_at:
        return "wait", minutes_until(prepare_at, now)
    if now < go_at:
        return "prep", minutes_until(go_at, now)
    if now <= go_at + timedelta(minutes=GRACE_MIN):
        return "go", 0
    return "late", 0


def progress(dep, now, prep_min, car_min):
    """-> (phase, seconds left in it, bar fill 0..1) for a countdown bar that drains.

    wait: time until you start getting ready (bar scale 30 min); prep: time until you must be in
    the car (scale = the prep time); go: slack left before it is too late (scale = GRACE_MIN)."""
    prepare_at, go_at = times(dep, prep_min, car_min)
    end = go_at + timedelta(minutes=GRACE_MIN)
    if now < prepare_at:
        left = (prepare_at - now).total_seconds()
        return "wait", left, min(1.0, left / 1800)
    if now < go_at:
        left = (go_at - now).total_seconds()
        return "prep", left, min(1.0, left / max(1.0, (go_at - prepare_at).total_seconds()))
    if now <= end:
        left = (end - now).total_seconds()
        return "go", left, min(1.0, left / (GRACE_MIN * 60))
    return "late", 0.0, 0.0


def pick(deps, now, prep_min, car_min):
    """-> (target, backup, missed). Target = first running train you can still catch,
    missed = the latest train it is too late for but that has not left yet."""
    ok, missed = [], []
    for d in deps:
        if d["cancelled"]:
            continue
        if phase(d, now, prep_min, car_min)[0] != "late":
            ok.append(d)
        elif d["real_dep"] > now:
            missed.append(d)
    return (ok[0] if ok else None), (ok[1] if len(ok) > 1 else None), (missed[-1] if missed else None)


class Alerts:
    """One chime when it is time to prepare, one when it is time to go; plus a delay change of
    >= 3 min and a cancellation. Each fires once per train."""

    def __init__(self):
        self.fired = set()
        self.last = {}  # train key -> (delay_min, cancelled)

    def check(self, target, now, prep_min, car_min, cancelled_seen=()):
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
        ph = phase(target, now, prep_min, car_min)[0]
        if ph == "go" and (key, "go") not in self.fired:
            self.fired |= {(key, "prepare"), (key, "go")}
            events.append(("go", target))
        elif ph == "prep" and (key, "prepare") not in self.fired:
            self.fired.add((key, "prepare"))
            events.append(("prepare", target))
        return events
