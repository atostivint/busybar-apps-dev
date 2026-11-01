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
import chime
import core
import gtfs
import rt

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
    p.add_argument("--work-min", type=int, default=10, help="evening: minutes from work to Rennes station")
    p.add_argument("--platform-home", default="", help="platform number at your station (blank = hide)")
    p.add_argument("--platform-rennes", default="", help="platform number at Rennes (blank = hide)")
    p.add_argument("--night", action="store_true", help="night theme: amber on black, dimmest")
    p.add_argument("--chime", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--chime-volume", type=int, default=40, help="0-100, chime loudness (the bar's master volume is untouched)")
    p.add_argument("--refresh", type=int, default=60, help="seconds between real-time refreshes")
    p.add_argument("--demo", action="store_true", help="ignore the windows (always active)")
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
        if e.code != 409:  # 409 = another app has the screen; keep trying
            print(f"draw failed: HTTP {e.code} {e.read()[:200]!r}", file=sys.stderr, flush=True)
    except (urllib.error.URLError, OSError) as e:
        print(f"cannot reach {base}: {e}", file=sys.stderr, flush=True)


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


SHORT = {"caulnes": "CAULNES", "la-brohiniere": "BROHIN.", "quedillac": "QUEDIL.", "rennes": "RENNES"}
PANEL_S, IDENT_S, LEAVE_S, CANCEL_S = 5, 3, 5, 4  # seconds each screen stays up


def screens(theme, target, cancelled, missed, now, buffer_min, platform, dest_name):
    """[(seconds, elements)] to rotate through. A cancelled train comes first, then the next one."""
    out = []
    if cancelled:
        out.append((CANCEL_S, board.panel(theme, f"{cancelled['dep']:%H:%M} {dest_name[:3]}", platform, cancelled=True)))
    if target is None:
        if not out:
            if missed:
                out.append((PANEL_S, board.message(theme, f"{missed['real_dep']:%H:%M} RATE", "Suivant ?", bad=True)))
            else:
                out.append((PANEL_S, board.message(theme, "Pas de train", "dans la plage")))
        return out
    lb = core.leave_by(target, buffer_min)
    left = core.minutes_until(lb, now)
    code = "RNS" if dest_name == "RENNES" else dest_name[:3]
    if left <= 0:  # time to go: nothing else matters
        return [(PANEL_S, board.leave(theme, 0, f"{lb:%H:%M}"))]
    out.append((PANEL_S, board.panel(theme, f"{target['real_dep']:%H:%M} {code}", platform,
                                     target["delay_min"])))
    out.append((IDENT_S, board.identity(theme, target["number"], dest_name)))
    out.append((LEAVE_S, board.leave(theme, left, f"{lb:%H:%M}")))
    return out


def pick_screen(seq, t):
    total = sum(s for s, _ in seq)
    t %= total
    for secs, els in seq:
        if t < secs:
            return els
        t -= secs
    return seq[-1][1]


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
    out_buffer = drive + a.parking_min + a.prep_min
    days = core.parse_days(a.days)
    ms, me = a.morning.split("-")
    es, ee = a.evening.split("-")
    windows = [core.Window("morning", days, core.parse_hhmm(ms), core.parse_hhmm(me), "out"),
               core.Window("evening", days, core.parse_hhmm(es), core.parse_hhmm(ee), "back")]
    sound = prepare_chime(base, a.chime_volume) if a.chime else None
    print(f"{a.station}: drive {drive} min, leave {out_buffer} min before departure", flush=True)

    table, table_day, feed, feed_at = None, None, {}, 0.0
    alerts = core.Alerts()
    shown, shown_ids = None, set()
    cleared = True
    try:
        while True:
            now = datetime.now(TZ)
            win = core.Window("demo", frozenset(range(7)), 0, 1440, "out") if a.demo \
                else core.active_window(now, windows)
            if win is None:
                if not cleared:
                    clear(base)
                    cleared, shown, shown_ids = True, None, set()
                time.sleep(30)
                continue
            try:
                if table is None or table_day != now.date():
                    table, table_day = gtfs.Timetable(), now.date()
                if time.time() - feed_at >= a.refresh:
                    feed, feed_at = rt.fetch(), time.time()
            except Exception as e:
                feed_at = time.time() - a.refresh + 15  # retry soon, keep the last feed
                print(f"data refresh failed: {e}", file=sys.stderr, flush=True)
                if table is None:
                    time.sleep(15)
                    continue

            out = win.direction == "out"
            origin, dest = (uic_home, uic_rns) if out else (uic_rns, uic_home)
            buffer_min = out_buffer if out else a.work_min
            sched = table.between(origin, dest, now.date(), TZ)
            deps = core.merge(sched, feed, origin, TZ)
            deps = [d for d in deps if d["real_dep"] > now - timedelta(minutes=2)]
            target, backup, missed = core.pick(deps, now, buffer_min)
            events = alerts.check(target, now, buffer_min,
                                  [d for d in deps if d["cancelled"] and d["dep"] > now])
            dest_name = SHORT["rennes"] if out else SHORT[a.station]
            platform = a.platform_home if out else a.platform_rennes
            canc = [d for d in deps if d["cancelled"] and d["dep"] > now]
            # a cancelled train only matters while it is before the one you will take
            cancelled = canc[0] if canc and (target is None or canc[0]["dep"] < target["dep"]) else None
            seq = screens("night" if a.night else "day", target, cancelled, missed, now, buffer_min,
                          platform, dest_name)
            els = pick_screen(seq, time.time())
            led = ALERT_LED if events else None
            if events and sound:
                try:
                    chime.play(base, APP, sound)
                except (urllib.error.URLError, OSError) as e:
                    print(f"chime failed: {e}", file=sys.stderr, flush=True)
            key = json.dumps(els)
            if key != shown or led:
                draw(base, els, led)
                ids = {e["id"] for e in els}
                remove(base, shown_ids - ids)
                shown, shown_ids, cleared = key, ids, False
            time.sleep(1 if events else 2)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        clear(base)


if __name__ == "__main__":
    main()
