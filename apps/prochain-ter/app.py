#!/usr/bin/env python3
"""Prochain TER: next TER home station <-> Rennes on the BUSY Bar (72x16 front display).

    python app.py                       # morning/evening windows, Caulnes
    python app.py --station quedillac
    python app.py --demo                # ignore the windows (always active), for testing

Data (no token): BreizhGo TER timetable (GTFS) + SNCF real-time trip updates, both from
transport.data.gouv.fr. Outside the commute windows the app draws nothing and does not poll.
The manager starts apps with --host 127.0.0.1:8321 and forwards draws to the bar.
Every argparse option below becomes a form control in the dashboard.
"""
import argparse
import json
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import board
import buttons
import chime
import core
import engine
import gtfs
import rt
import sim
import traffic

APP = "prochain-ter"
TZ = ZoneInfo("Europe/Paris")
HERE = Path(__file__).resolve().parent
ALERT_LED = "#FFAA00FF"


def args():
    p = argparse.ArgumentParser(description="Next TER to Rennes / back home")
    p.add_argument("--host", default="10.0.4.20")
    p.add_argument("--station", default="caulnes", choices=["caulnes", "la-brohiniere", "quedillac"])
    p.add_argument("--morning", default="06:00-09:00", help="HH:MM-HH:MM, station -> Rennes")
    p.add_argument("--evening", default="16:30-19:30", help="HH:MM-HH:MM, Rennes -> station")
    p.add_argument("--days", default="mon,tue,wed,thu,fri")
    p.add_argument("--prep-min", type=int, default=5, help="minutes to get ready before driving")
    p.add_argument("--parking-min", type=int, default=3, help="parking + walk to the platform")
    p.add_argument("--drive-min", type=int, default=0, help="0 = use drive_times.json")
    p.add_argument("--slack-min", type=int, default=3, help="minutes after GO during which leaving still works")
    p.add_argument("--work-min", type=int, default=10, help="evening: minutes from work to Rennes station")
    p.add_argument("--platform-home", default="", help="platform number at your station (blank = hide)")
    p.add_argument("--platform-rennes", default="", help="platform number at Rennes (blank = hide)")
    p.add_argument("--night", action="store_true", help="night theme: amber on black, dimmest")
    p.add_argument("--show-ahead", type=int, default=15,
                   help="minutes before you must start preparing that the screen takes over (else it stays blank)")
    p.add_argument("--snooze-button", default="start", choices=["start", "ok", "back", "off"],
                   help="bar button that dismisses the train on screen")
    p.add_argument("--work-address", default="", help="your work address: shows the live drive time when no train is left")
    p.add_argument("--chime", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--engine", action=argparse.BooleanOptionalAction, default=True,
                   help="play an engine start-up instead of the chime when it is time to go")
    p.add_argument("--chime-volume", type=int, default=40, help="0-100, chime loudness (the bar's master volume is untouched)")
    p.add_argument("--refresh", type=int, default=60, help="seconds between real-time refreshes")
    p.add_argument("--demo", action="store_true", help="ignore the windows (always active)")
    p.add_argument("--simulate", action="store_true", help="play a fake train on a fast clock (see sim.py)")
    p.add_argument("--sim-speed", type=int, default=20, help="simulation: simulated seconds per real second")
    return p.parse_args()


def call(base, path, method="GET", body=None, timeout=5):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def clear(base):
    q = urllib.parse.urlencode({"application_name": APP})
    try:
        call(base, "/api/display/draw?" + q, "DELETE")
    except (urllib.error.URLError, OSError):
        pass


def draw(base, elements, led=None):
    body = {"application_name": APP, "priority": 60, "elements": elements}
    if led:
        body["led_notification_color"] = led
    try:
        call(base, "/api/display/draw", "POST", body)
    except urllib.error.HTTPError as e:
        if e.code != 409:
            print(f"draw failed: HTTP {e.code} {e.read()[:200]!r}", file=sys.stderr, flush=True)
        elif time.time() - draw.last409 > 30:  # 409 = another app holds the screen; keep trying
            draw.last409 = time.time()
            print(f"draw refused (409): {e.read()[:120]!r}", file=sys.stderr, flush=True)
    except (urllib.error.URLError, OSError) as e:
        print(f"cannot reach {base}: {e}", file=sys.stderr, flush=True)


draw.last409 = 0.0


def remove(base, ids):
    """Elements persist by id: drop the ones the new screen no longer has."""
    if not ids:
        return
    try:
        call(base, "/api/display/draw", "DELETE", {"application_name": APP, "element_ids": sorted(ids)})
    except (urllib.error.URLError, OSError):
        pass


def prepare_chime(base, volume):
    """Upload the chime (your own chime.snd if present, else the synthesised 4 notes). -> remote name or None."""
    own = HERE / "chime.snd"
    local = own
    if not own.exists():
        local = HERE / "cache" / "chime.snd"
        local.parent.mkdir(exist_ok=True)
        chime.build_wav(local, volume)
    try:
        chime.upload(base, APP, local, "chime.snd")
        return "chime.snd"
    except (urllib.error.URLError, OSError) as e:
        print(f"chime upload failed, running silent: {e}", file=sys.stderr, flush=True)
        return None


def prepare_engine(base, volume):
    """Upload the engine start-up (your own engine.snd if present). -> remote name or None."""
    local = HERE / "engine.snd"
    if not local.exists():
        local = HERE / "cache" / "engine.snd"
        local.parent.mkdir(exist_ok=True)
        engine.build_wav(local, volume)
    try:
        chime.upload(base, APP, local, "engine.snd")
        return "engine.snd"
    except (urllib.error.URLError, OSError) as e:
        print(f"engine upload failed, using the chime: {e}", file=sys.stderr, flush=True)
        return None


SHORT = {"caulnes": "CAULNES", "la-brohiniere": "BROHIN.", "quedillac": "QUEDIL.", "rennes": "RENNES"}
PANEL_S, IDENT_S, STEP_S, CANCEL_S, LATE_S, CLOCK_S = 4, 5, 9, 4, 9, 4  # seconds each screen stays up


def screens(theme, target, cancelled, missed, now, prep_min, car_min, platform, dest_name, intro=False, drive=None):
    """[(seconds, elements)] to rotate through.

    Order: a cancelled train, "too late" for a train you can no longer catch (with the next one to
    wait for), then the train you will take: step screen (the countdown), clock, panel.
    The TER logo (identity) is shown once when a train comes up (`intro`), then never again.
    At GO the countdown is shown alone, so it cannot be missed."""
    out = []
    if cancelled:
        out.append((CANCEL_S, board.info(theme, f"{cancelled['dep']:%H:%M}", cancelled=True)))
    if target is None:
        if missed:
            out.append((LATE_S, board.next_train(theme, drive=drive)))
        elif not out:
            out.append((PANEL_S, board.next_train(theme, drive=drive)))
        return out
    ph, left_s, frac = core.progress(target, now, prep_min, car_min)
    dep = f"{target['real_dep']:%H:%M}"
    go_at = core.times(target, prep_min, car_min)[1]
    step = board.steps(theme, ph, left_s, frac, f"{go_at:%H:%M}", dep)
    if intro and ph != "go":
        return [(IDENT_S, board.identity(theme, target["number"], dest_name))]
    if ph == "go":
        return [(STEP_S, step)]
    if missed:
        out.append((LATE_S, board.next_train(theme, dep, f"{go_at:%H:%M}")))
    out.append((STEP_S, step))
    out.append((CLOCK_S, board.clock(theme, f"{now:%H:%M}", dest_name)))
    out.append((PANEL_S, board.info(theme, dep, target["delay_min"])))
    return out


def pick_screen(seq, t):
    total = sum(s for s, _ in seq)
    t %= total
    for secs, els in seq:
        if t < secs:
            return els
        t -= secs
    return seq[-1][1]


def visible(target, cancelled, missed, deps, now, prep_min, car_min, ahead):
    """The screen only takes over when a train is about to matter: `ahead` minutes before you must
    start getting ready, while a train is too late to catch, and for a moment after the last one."""
    def soon(d):
        return now >= core.times(d, prep_min, car_min)[0] - timedelta(minutes=ahead)
    if missed or (target and soon(target)) or (cancelled and soon(cancelled)):
        return True
    return target is None and any(not d["cancelled"] and d["real_dep"] <= now for d in deps)


def main():
    a = args()
    base = "http://" + a.host.replace("http://", "").rstrip("/")
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    clear(base)  # a hard kill (Windows) skips `finally`; wipe leftovers from a previous run

    uic_home, uic_rns = gtfs.STATIONS[a.station][0], gtfs.STATIONS["rennes"][0]
    try:
        drive = json.loads((HERE / "drive_times.json").read_text())["drive_min"][a.station]
    except (OSError, KeyError, ValueError):
        drive = 10
    if a.drive_min:
        drive = a.drive_min
    core.GRACE_MIN = a.slack_min
    car_min = drive + a.parking_min  # from leaving the house to the platform
    days = core.parse_days(a.days)
    ms, me = a.morning.split("-")
    es, ee = a.evening.split("-")
    windows = [core.Window("morning", days, core.parse_hhmm(ms), core.parse_hhmm(me), "out"),
               core.Window("evening", days, core.parse_hhmm(es), core.parse_hhmm(ee), "back")]
    sound = prepare_chime(base, a.chime_volume) if a.chime else None
    engine_sound = prepare_engine(base, a.chime_volume) if (a.chime and a.engine) else None
    print(f"{a.station}: prepare {a.prep_min} min, then {car_min} min to the platform (drive {drive})", flush=True)

    table, table_day, feed, feed_at = None, None, {}, 0.0
    alerts = core.Alerts()
    clock = sim.Clock(a.sim_speed, TZ) if a.simulate else None
    key = traffic.load_key()
    live = None
    if key and a.work_address:
        try:
            home = json.loads((HERE / "drive_times.json").read_text())["home"]
            live = traffic.Traffic(key, (home["lat"], home["lon"]), a.work_address)
        except (OSError, KeyError, ValueError):
            print("traffic: run tools/prochain_drive_times.py first (needs your home position)", flush=True)
    shown, shown_ids = None, set()
    intro_seen, intro_until = set(), 0.0
    snoozed = set()  # trains you dismissed with the button
    pad = buttons.Buttons(a.host, a.snooze_button) if a.snooze_button != "off" else None
    ahead = 60 if clock else a.show_ahead
    cleared = True
    try:
        while True:
            now = clock.now() if clock else datetime.now(TZ)
            if clock and clock.done():
                break
            win = core.Window("demo", frozenset(range(7)), 0, 1440, "out") if (a.demo or clock) \
                else core.active_window(now, windows)
            if win is None:
                if not cleared:
                    clear(base)
                    cleared, shown, shown_ids = True, None, set()
                time.sleep(30)
                continue
            try:
                if clock:
                    pass
                elif table is None or table_day != now.date():
                    table, table_day = gtfs.Timetable(), now.date()
                if not clock and time.time() - feed_at >= a.refresh:
                    feed, feed_at = rt.fetch(), time.time()
            except Exception as e:
                feed_at = time.time() - a.refresh + 15  # retry soon, keep the last feed
                print(f"data refresh failed: {e}", file=sys.stderr, flush=True)
                if table is None:
                    time.sleep(15)
                    continue

            out = win.direction == "out"
            origin, dest = (uic_home, uic_rns) if out else (uic_rns, uic_home)
            prep_min, car = (a.prep_min, car_min) if out else (0, a.work_min)  # evening: no prep, just the way
            if clock:
                deps = sim.departures(clock)
            else:
                sched = table.between(origin, dest, now.date(), TZ)
                deps = core.merge(sched, feed, origin, TZ)
            deps = [d for d in deps if d["real_dep"] > now - timedelta(minutes=2)
                    and (d["number"], d["date"]) not in snoozed]
            target, backup, missed = core.pick(deps, now, prep_min, car)
            canc = [d for d in deps if d["cancelled"] and d["dep"] > now]
            # a cancelled train only matters while it is before the one you will take
            cancelled = canc[0] if canc and (target is None or canc[0]["dep"] < target["dep"]) else None
            show = visible(target, cancelled, missed, deps, now, prep_min, car, ahead)
            if pad and pad.pressed() and show:  # snooze: dismiss what is on screen, stop the sound
                snoozed |= {(d["number"], d["date"]) for d in (target, cancelled, missed) if d}
                try:
                    chime.stop(base, APP)
                except (urllib.error.URLError, OSError):
                    pass
                continue
            if not show:  # nothing coming up: leave the bar to its other apps
                if not cleared:
                    clear(base)
                    cleared, shown, shown_ids = True, None, set()
                time.sleep(3)
                continue
            events = alerts.check(target, now, prep_min, car, canc)
            dest_name = SHORT["rennes"] if out else SHORT[a.station]
            platform = a.platform_home if out else a.platform_rennes
            if target and (target["number"], target["date"]) not in intro_seen:
                intro_seen.add((target["number"], target["date"]))
                intro_until = time.time() + IDENT_S  # the TER logo, once per train
            seq = screens("night" if a.night else "day", target, cancelled, missed, now, prep_min, car,
                          platform, dest_name, intro=time.time() < intro_until,
                          drive=live.get() if (live and target is None) else None)
            els = pick_screen(seq, time.time())
            led = ALERT_LED if events else None
            if events and sound:
                kinds = {k for k, _ in events}
                try:
                    chime.play(base, APP, engine_sound if ("go" in kinds and engine_sound) else sound)
                except (urllib.error.URLError, OSError) as e:
                    print(f"chime failed: {e}", file=sys.stderr, flush=True)
            frame = json.dumps(els)
            if frame != shown or led:
                draw(base, els, led)
                ids = {e["id"] for e in els}
                remove(base, shown_ids - ids)
                shown, shown_ids, cleared = frame, ids, False
            time.sleep(1 if events or (target and core.phase(target, now, prep_min, car)[0] == "go") else 2)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        clear(base)


if __name__ == "__main__":
    main()
