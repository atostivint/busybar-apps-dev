#!/usr/bin/env python3
"""Halloween Clock: time in the middle, pumpkin on the left, bat on the right.

    python app.py                              # graveyard scene, 24h clock, orange
    python app.py --style classic              # pumpkin + bat sprites
    python app.py --hour12 --color "#FF7A00FF"
    python app.py --host 127.0.0.1:8080        # emulator

Two styles: "graveyard" (default; one full-bar scene with a tree, moon, tombstones
and a bat crossing behind the time) and "classic" (pumpkin left, bat right).
The animations are .anim files in assets/ (made by tools/gen_halloween.py and
tools/gen_graveyard.py). They are uploaded once at startup and then played by
the firmware itself, so the app only sends a request when the minute changes.
"""
import argparse
import json
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
# Animations played by the firmware, per style: (element id, file, x, y)
STYLES = {
    "graveyard": [("scene", "graveyard.anim", 0, 0)],
    "classic": [("pumpkin", "pumpkin.anim", 0, 0), ("bat", "bat.anim", 56, 0)],
}


def _color(value):
    value = value.strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}([0-9a-fA-F]{2})?", value):
        raise argparse.ArgumentTypeError("color must be RRGGBB or RRGGBBAA")
    return "#" + (value + "FF" if len(value) == 6 else value).upper()


def args():
    p = argparse.ArgumentParser(description="Halloween clock with animated pumpkin and bat")
    p.add_argument("--host", default="10.0.4.20")
    p.add_argument("--style", choices=sorted(STYLES), default="graveyard", help="which animation to play")
    p.add_argument("--color", type=_color, default="#FF7A00FF", help="time color, RRGGBB or RRGGBBAA")
    p.add_argument("--hour12", action="store_true", help="12-hour clock instead of 24-hour")
    p.add_argument("--priority", type=int, default=50, help="draw priority 1-100 (default 50)")
    return p.parse_args()


def call(base, path, method="GET", body=None, raw=None, ctype="application/json"):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": ctype} if data else {})
    with urllib.request.urlopen(req, timeout=5):
        pass


def upload(base, name):
    q = urllib.parse.urlencode({"application_name": APP, "file": name})
    data = (ASSETS / name).read_bytes()
    for attempt in range(3):  # 508 = asset briefly locked by the display
        try:
            call(base, "/api/assets/upload?" + q, "POST", raw=data, ctype="application/octet-stream")
            return
        except urllib.error.HTTPError as e:
            if e.code == 508 and attempt < 2:
                time.sleep(0.2)
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
        h = now.tm_hour % 12 or 12
        return f"{h}:{now.tm_min:02d}"
    return f"{now.tm_hour:02d}:{now.tm_min:02d}"


def main():
    a = args()
    base = "http://" + a.host.replace("http://", "").rstrip("/")
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    sprites_drawn, shown = False, None
    uploaded = False
    # On Windows the manager stops apps with a hard kill, so the cleanup in `finally`
    # may never run. Wipe whatever a previous run (or style) left on the bar.
    clear(base)
    try:
        while True:
            try:
                if not uploaded:
                    for _, name, _, _ in STYLES[a.style]:
                        upload(base, name)
                    uploaded = True
                now = time.localtime()
                text = clock_text(now, a.hour12)
                elements = []
                if not sprites_drawn:
                    elements += [{"id": eid, "type": "animation", "path": name, "x": x, "y": y, "loop": True}
                                 for eid, name, x, y in STYLES[a.style]]
                if text != shown or not sprites_drawn:
                    elements.append({"id": "time", "type": "text", "text": text, "font": "extra_large",
                                     "color": a.color, "x": 36, "y": 8, "align": "center"})
                if elements:
                    call(base, "/api/display/draw", "POST",
                         {"application_name": APP, "priority": a.priority, "elements": elements})
                    sprites_drawn, shown = True, text
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
