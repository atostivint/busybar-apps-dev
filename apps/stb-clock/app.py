#!/usr/bin/env python3
"""Steal These Buttons: one whole classic web button at a time, with the time on its own bar.

    python app.py                     # 10 s per button, clock bar along the bottom
    python app.py --hold 30           # slower
    python app.py --no-shuffle        # keep the collection's filename order

The manager starts the app with --host 127.0.0.1:8321 and proxies to the bar.

The front display is 72x16, so an 80x15 button is fitted to 72x15 and drawn at the top: the whole
button is visible and fills almost the whole screen. Resampling would turn the 5 px button text into
grey mush, so each badge is reduced to 32 colours first, resized, then snapped back to that palette:
flat areas stay flat and the strokes stay sharp. The time is drawn on top of the image, only its own pixels:
black or white 3x5 digits, whichever contrasts with the part of the button underneath, so nothing
around the clock is painted.

Draws are rare on purpose: one when the badge swaps (a hard cut, no sliding, no animation) and one
at each minute boundary, when the clock text changes. A draw costs the bar ~40-110 ms and frequent
draws made it glitch, so there is no frame timer and no continuous redraw. Each draw sends the whole
scene (badge first, bar last) because an element that arrives alone can end up behind the others.
"""
import argparse
import json
import random
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import belt
import layout
from controls import Controls

APP = "stb-clock"
HERE = Path(__file__).resolve().parent


def args():
    p = argparse.ArgumentParser(description="One whole classic web button at a time, with the time")
    p.add_argument("--host", default="10.0.4.20", help="bar address (the manager passes its own)")
    p.add_argument("--hold", type=int, default=10, help="seconds each button stays on screen (3-120)")
    p.add_argument("--clock", default="auto", choices=("auto",) + layout.CORNERS,
                   help="clock corner: auto = emptiest spot")
    p.add_argument("--wheel", default="on", choices=("on", "off"),
                   help="wheel switches picture")
    p.add_argument("--outline", default="off", choices=("on", "off"),
                   help="black halo around the digits")
    p.add_argument("--clock-color", default="auto", choices=("inverse", "auto"),
                   help="digit colour: black/white or inverse")
    p.add_argument("--start", type=int, default=0, help="badge index to start on")
    p.add_argument("--shuffle", default="on", choices=("on", "off"),
                   help="shuffle the order at start")
    p.add_argument("--priority", type=int, default=60, help="display priority 1-100")
    return p.parse_args()


_last_log = 0.0


def report(msg):
    """One line per 30 s at most: a bar that is off must not flood the manager's log."""
    global _last_log
    now = time.monotonic()
    if now - _last_log >= 30:
        _last_log = now
        print(msg, file=sys.stderr, flush=True)


def call(base, path, method="GET", body=None, timeout=4):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def clear(base):
    """Windows: the manager kills the process, `finally` never runs, so always clear on start."""
    try:
        call(base, "/api/display/draw?" + urllib.parse.urlencode({"application_name": APP}), "DELETE")
    except (urllib.error.HTTPError, urllib.error.URLError, OSError):
        pass


def draw(base, elements, priority):
    """One draw request. A 409 means another app holds the screen; the next wake retries."""
    body = {"application_name": APP, "priority": priority, "elements": elements}
    try:
        call(base, "/api/display/draw", "POST", body)
        return True
    except urllib.error.HTTPError as e:
        if e.code == 409:
            report(f"{base}: screen held by another app (HTTP 409)")
        else:
            report(f"draw failed: HTTP {e.code} {e.read()[:200]!r}")
    except (urllib.error.URLError, OSError) as e:
        report(f"cannot reach {base}: {e}")
    return False


def main():
    a = args()
    base = "http://" + a.host.replace("http://", "").rstrip("/")
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    badges = belt.load(HERE / "assets" / "buttons")
    if not badges:
        sys.exit("no badges in assets/buttons (run tools/fetch_buttons.py)")
    if a.shuffle == "on":
        random.shuffle(badges)
    n = len(badges)
    index = max(0, min(n - 1, a.start))
    hold = max(3, min(120, a.hold))
    corner = a.clock if a.clock != "auto" else layout.choose_corner(badges[index], "00:00")

    controls = Controls(base) if a.wheel == "on" else None

    print(f"{n} badges at {badges[0].w}x{badges[0].h}, hold {hold} s, clock {a.clock}"
          f", "
          f"{'wheel on' if controls else 'wheel off'}, start {badges[index].name}", flush=True)
    clear(base)

    # Swap times follow the monotonic clock so a slow draw cannot accumulate drift; the minute
    # boundary comes from the wall clock, because that is what the digits show.
    swap_due = time.monotonic() + hold
    last_hhmm = None
    pick_corner = True
    while True:
        # Advance first, then draw once: a swap costs one draw, not one redraw of the old badge.
        woke = time.monotonic()
        if woke >= swap_due:
            index = (index + 1) % n
            pick_corner = True
            swap_due += hold
            if swap_due <= woke:        # stalled for longer than a period: re-anchor, never burst
                swap_due = woke + hold

        wall = time.time()
        hhmm = time.strftime("%H:%M", time.localtime(wall))
        if a.clock == "auto" and pick_corner:
            corner = layout.choose_corner(badges[index], hhmm, corner)
            pick_corner = False
        badge = badges[index]
        align = layout.choose_align(badge, corner, hhmm)
        plate = layout.needs_plate(badge, corner, hhmm, align)
        outline = not plate and (a.outline == "on" or layout.needs_outline(badge, corner, hhmm, align))
        els = layout.elements(badge, index, hhmm, corner, a.clock_color, outline, plate, align)
        draw(base, els, a.priority)

        if hhmm != last_hhmm:
            print(time.strftime("%Y-%m-%d %H:%M", time.localtime(wall)), flush=True)
            last_hhmm = hhmm

        # Wait for the next badge swap, the next minute boundary, or the wheel. If the draw itself
        # straddled the boundary, the digits on the bar are a minute old: wake at once and draw again.
        wall = time.time()
        if time.strftime("%H:%M", time.localtime(wall)) != hhmm:
            wait = 0.05
        else:
            wait = 60.05 - (wall % 60.0)
        timeout = max(0.05, min(swap_due - time.monotonic(), wait))
        if controls is None:
            time.sleep(timeout)
            turned = False
        else:
            turned = controls.wait(timeout)
        if turned:
            steps, clicks = controls.take()
            if steps or clicks:
                index = (index + steps + (1 if clicks else 0)) % n
                pick_corner = True
                swap_due = time.monotonic() + hold      # the manual pick gets a full hold


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
