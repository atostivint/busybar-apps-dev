#!/usr/bin/env python3
"""FUI Clock: a clock in many sci-fi HUD designs for the BUSY Bar, rendered on the computer.

    python app.py --design radar --accent amber
    python app.py --design all --rotate 2          # cycle through every design, two minutes each
    python -m fui.gallery --out gallery.html       # see them all without the bar

The bar cannot draw a clock, it plays files. So every minute is rendered ahead as one 60 s animation (digits,
seconds hand and ambient motion all baked in), uploaded under one of two alternating names (the bar locks the
file it is playing), and started on the minute. The firmware does the rest: one request a minute.
Every flag is a form control in the manager's dashboard; changing one means a restart, which the manager does.
"""
import json
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from fui.cli import ACCENTS, SWATCH, build_parser, colour
from fui.controls import Controls
from fui.designs import DESIGNS, SHAPES
from fui.render import parse_zones, pick, render_minute, write

APP = "fui-clock"
ASSETS = Path(__file__).resolve().parent / "assets"
LEAD = 0.15     # s: post the draw this long before the minute, the bar takes a moment to start it
FAST = 3.5     # s: after a wheel change, start this far ahead (the render is ~2 s)
MARGIN = 8.0    # s: at startup, begin the first animation this far into the minute (render + upload time)


def call(base, path, method="GET", body=None, raw=None, ctype="application/json", timeout=5):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(base + path, data=data, method=method, headers={"Content-Type": ctype} if data else {})
    with urllib.request.urlopen(req, timeout=timeout):
        pass


def upload(base, name):
    q = urllib.parse.urlencode({"application_name": APP, "file": name})
    data = (ASSETS / name).read_bytes()
    for attempt in range(6):  # 508 = asset briefly locked by the display, 408 = slow upload
        try:
            call(base, "/api/assets/upload?" + q, "POST", raw=data, ctype="application/octet-stream", timeout=60)
            return
        except urllib.error.HTTPError as e:
            if e.code in (408, 508) and attempt < 5:
                time.sleep(0.5 + attempt)
                continue
            raise
        except (urllib.error.URLError, OSError) as e:
            if attempt == 5:
                raise
            print(f"upload retry: {e}", file=sys.stderr)
            time.sleep(1 + attempt)


def clear(base):
    """Wipe this app's elements; the manager hard-kills apps on Windows, so `finally` may never run."""
    try:
        call(base, "/api/display/draw?" + urllib.parse.urlencode({"application_name": APP}), "DELETE")
    except (urllib.error.URLError, OSError):
        pass


def draw(base, name, priority, give_up):
    """Start the animation; keep trying while another app holds the screen, until `give_up` (epoch)."""
    element = {"id": "clock", "type": "animation", "path": name, "x": 0, "y": 0, "loop": True}
    while time.time() < give_up:
        try:
            call(base, "/api/display/draw", "POST", body={"application_name": APP, "priority": priority, "elements": [element]})
            return True
        except urllib.error.HTTPError as e:
            if e.code != 409:  # 409 = another app has the screen
                print(f"draw failed: HTTP {e.code}", file=sys.stderr)
        except (urllib.error.URLError, OSError) as e:
            print(f"cannot reach {base}: {e}", file=sys.stderr)
        time.sleep(2)
    return False


class Selection:
    """What the wheel has chosen so far: design, accent colour and alarm sign. Applied once the wheel pauses."""
    SETTLE = 0.6  # s without wheel movement before the change is rendered

    def __init__(self, a, controls):
        self.names = list(DESIGNS)
        self.cycle = a.design == "all"
        self.design = a.design if a.design != "all" else self.names[0]
        self.accent, self.alarm_colour, self.alarm_shape = a.accent, a.alarm_colour, a.alarm_shape
        self.controls, self.changed_at, self.dirty = controls, 0.0, False
        self.swatches = [colour(n) for n in SWATCH]

    def poll(self):
        """Fold in wheel input; True once a change is pending and the wheel has settled."""
        if self.controls:
            steps, clicks = self.controls.take()
            if steps:
                self.cycle = False
                i = (self.names.index(self.design) + steps) % len(self.names)
                self.design = self.names[i]
            if clicks:
                if self.design == "alarm":
                    self.alarm_shape = SHAPES[(SHAPES.index(self.alarm_shape) + 1) % len(SHAPES)]
                else:
                    i = self.swatches.index(self.accent) if self.accent in self.swatches else -1
                    self.accent = self.swatches[(i + 1) % len(self.swatches)]
            if steps or clicks:
                self.changed_at, self.dirty = time.time(), True
        return self.dirty and time.time() - self.changed_at >= self.SETTLE


def wait_until(t, sel):
    """Sleep until epoch t; returns True early if the wheel changed something."""
    while (d := t - time.time()) > 0:
        if sel.poll():
            return True
        time.sleep(min(d, 0.1))
    return sel.poll()


def main():
    a = build_parser("FUI Clock: sci-fi HUD clock designs, rendered on the computer").parse_args()
    base = "http://" + a.host.replace("http://", "").rstrip("/")
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    zones, order, fps = parse_zones(a.zones), list(DESIGNS), a.fps
    sel = Selection(a, None if a.no_wheel else Controls(a.host))
    ASSETS.mkdir(exist_ok=True)
    clear(base)
    slot, last, switched = 0, None, False
    try:
        while True:
            now = time.time()
            E0 = int(now // 60) * 60
            lead = FAST if switched else MARGIN
            if (last is None or switched) and now - E0 + lead < 56:  # start mid-minute, in step with the seconds
                E, first = E0, int((now - E0 + lead) * fps) + 1
            else:  # render the next minute ahead and start it on the dot
                E = (last + 60) if last is not None and last > E0 else E0 + 60
                if E - now < 3:  # running late (slow render or a stalled upload): skip to the next minute
                    E = int((now + 3) // 60) * 60 + 60
                first = 0
            last = E
            sel.dirty = False
            design = sel.design if not sel.cycle else pick("all", E, a.rotate, order)
            t0 = time.time()
            frames = render_minute(design, E, fps, sel.accent, a.hour12, not a.steady_colon, zones, a.min_alpha,
                                   (sel.alarm_colour, sel.alarm_shape), first=first, prev=first == 0,
                                   toast_until=(first / fps + 1.5) if switched and first else 0.0)
            name = f"fui_clock_{slot}.anim"
            slot ^= 1
            write(ASSETS / name, frames, fps)
            upload(base, name)
            print(f"{time.strftime('%H:%M', time.localtime(E))} {design}: {len(frames)} frames in {time.time() - t0:.1f}s",
                  flush=True)
            if wait_until(E + first / fps - LEAD, sel):  # the wheel moved while waiting: redo it for the new choice
                switched, last = True, E - 60
                continue
            switched = False
            draw(base, name, a.priority, E + 55)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        clear(base)


if __name__ == "__main__":
    main()
