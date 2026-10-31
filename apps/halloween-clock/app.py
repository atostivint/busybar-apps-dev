#!/usr/bin/env python3
"""Halloween Clock: orange time over an animated night scene.

    python app.py                              # graveyard scene, 24h clock
    python app.py --style classic              # pumpkin + bat sprites, no random events
    python app.py --hour12 --color "#FF7A00FF"
    python app.py --bat-min 10 --bat-max 30    # bat every 10-30 s (random)
    python app.py --thunder-max 0              # no thunder
    python app.py --host 127.0.0.1:8080        # emulator

"graveyard" (default): a looping base scene (tree, pumpkin, moon with drifting clouds,
stars, a soft glow behind the time) plus two kinds of random events played on top at
random intervals: a bat crossing the bar (4 variants: direction x altitude) and a
thunderstorm flash. "classic": pumpkin on the left, bat flapping on the right.

The animations are .anim files in assets/ (see tools/gen_halloween.py and
tools/gen_graveyard.py). They are uploaded once at startup and played by the firmware
itself, so the app only sends a request when the minute changes or an event fires.
"""
import argparse
import json
import random
import re
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

APP = "halloween-clock"
ASSETS = Path(__file__).resolve().parent / "assets"

# Looping animations per style: (element id, file, x, y)
BASE = {
    "graveyard": [("scene", "graveyard.anim", 0, 0)],
    "classic": [("pumpkin", "pumpkin.anim", 0, 0), ("bat", "bat.anim", 56, 0)],
}
BATS = ["bat_lr_high.anim", "bat_rl_high.anim", "bat_lr_low.anim", "bat_rl_low.anim"]
BAT_SECONDS, THUNDER_SECONDS = 3.0, 0.8  # one-shot lengths (frames / 20 fps)
EVENT_FILES = BATS + ["thunder.anim"]


def _color(value):
    value = value.strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}([0-9a-fA-F]{2})?", value):
        raise argparse.ArgumentTypeError("color must be RRGGBB or RRGGBBAA")
    return "#" + (value + "FF" if len(value) == 6 else value).upper()


def args():
    p = argparse.ArgumentParser(description="Halloween clock with an animated night scene")
    p.add_argument("--host", default="10.0.4.20")
    p.add_argument("--style", choices=sorted(BASE), default="graveyard", help="which scene to play")
    p.add_argument("--color", type=_color, default="#FF7A00FF", help="time color, RRGGBB or RRGGBBAA")
    p.add_argument("--hour12", action="store_true", help="12-hour clock instead of 24-hour")
    p.add_argument("--bat-min", type=int, default=20, help="shortest wait between bat flights, seconds")
    p.add_argument("--bat-max", type=int, default=60, help="longest wait between bat flights (0 = no bats)")
    p.add_argument("--thunder-min", type=int, default=30, help="shortest wait between thunderstorms, seconds")
    p.add_argument("--thunder-max", type=int, default=120, help="longest wait between thunderstorms (0 = none)")
    p.add_argument("--priority", type=int, default=50, help="draw priority 1-100 (default 50)")
    return p.parse_args()


def call(base, path, method="GET", body=None, raw=None, ctype="application/json", timeout=5):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": ctype} if data else {})
    with urllib.request.urlopen(req, timeout=timeout):
        pass


def upload(base, name):
    q = urllib.parse.urlencode({"application_name": APP, "file": name})
    data = (ASSETS / name).read_bytes()
    for attempt in range(3):  # 508 = asset briefly locked by the display
        try:
            call(base, "/api/assets/upload?" + q, "POST", raw=data, ctype="application/octet-stream", timeout=20)
            return
        except urllib.error.HTTPError as e:
            if e.code == 508 and attempt < 2:
                time.sleep(0.3)
                continue
            raise


def clear(base):
    q = urllib.parse.urlencode({"application_name": APP})
    try:
        call(base, "/api/display/draw?" + q, "DELETE")
    except (urllib.error.URLError, OSError):
        pass


def clock_text(now, hour12):
    if hour12:
        return f"{now.tm_hour % 12 or 12}:{now.tm_min:02d}"
    return f"{now.tm_hour:02d}:{now.tm_min:02d}"


def schedule(lo, hi):
    """Next event time (monotonic), or None when disabled."""
    return time.monotonic() + random.uniform(lo, max(lo, hi)) if hi > 0 else None


def main():
    a = args()
    base = "http://" + a.host.replace("http://", "").rstrip("/")
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    events_on = a.style == "graveyard"

    def time_element(text):
        return {"id": "time", "type": "text", "text": text, "font": "extra_large",
                "color": a.color, "x": 36, "y": 8, "align": "center"}

    def send(elements):
        call(base, "/api/display/draw", "POST",
             {"application_name": APP, "priority": a.priority, "elements": elements})

    base_drawn, shown, uploaded = False, None, False
    next_bat = next_thunder = None
    # On Windows the manager stops apps with a hard kill, so the cleanup in `finally`
    # may never run. Wipe whatever a previous run (or style) left on the bar.
    clear(base)
    try:
        while True:
            try:
                if not uploaded:
                    files = [f for _, f, _, _ in BASE[a.style]] + (EVENT_FILES if events_on else [])
                    for name in files:
                        upload(base, name)
                    uploaded = True
                    if events_on:
                        next_bat, next_thunder = schedule(a.bat_min, a.bat_max), schedule(a.thunder_min, a.thunder_max)
                text = clock_text(time.localtime(), a.hour12)
                elements = []
                if not base_drawn:
                    elements += [{"id": eid, "type": "animation", "path": f, "x": x, "y": y, "loop": True}
                                 for eid, f, x, y in BASE[a.style]]
                if text != shown or not base_drawn:
                    elements.append(time_element(text))
                if elements:
                    send(elements)
                    base_drawn, shown = True, text

                # Random one-shot events. The time is re-sent after each one so it stays on top.
                now = time.monotonic()
                if events_on and base_drawn:
                    fired = []
                    if next_bat and now >= next_bat:
                        fired.append({"id": "bat", "type": "animation", "path": random.choice(BATS),
                                      "x": 0, "y": 0, "loop": False, "timeout": BAT_SECONDS + 0.4})
                        next_bat = schedule(a.bat_min, a.bat_max)
                    if next_thunder and now >= next_thunder:
                        fired.append({"id": "thunder", "type": "animation", "path": "thunder.anim",
                                      "x": 0, "y": 0, "loop": False, "timeout": THUNDER_SECONDS + 0.4})
                        next_thunder = schedule(a.thunder_min, a.thunder_max)
                    if fired:
                        send(fired + [time_element(shown)])
            except urllib.error.HTTPError as e:
                if e.code != 409:  # 409: another app outranks us right now; retry
                    print(f"request failed: HTTP {e.code} {e.read().decode(errors='replace')[:200]}",
                          file=sys.stderr, flush=True)
            except urllib.error.URLError as e:
                print(f"cannot reach {base}: {e.reason}", file=sys.stderr, flush=True)
            time.sleep(1.0)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        clear(base)


if __name__ == "__main__":
    main()
