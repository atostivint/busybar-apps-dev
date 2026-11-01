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
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from fui.cli import ACCENTS, SWATCH, build_parser, colour
from fui.controls import Controls
from fui.designs import DESIGNS, SHAPES
from fui.render import parse_zones, pick, render_at, render_minute, write

APP = "fui-clock"
ASSETS = Path(__file__).resolve().parent / "assets"
LEAD = 0.15     # s: post the draw this long before the minute, the bar takes a moment to start it
FAST = 1.2     # s: after a wheel change, start this far ahead (a short clip renders in ~0.3 s)
CLIP = 8.0     # s: that first clip is short so it is quick; the rest of the minute follows it
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
            if e.code in (408, 502, 503, 508) and attempt < 5:
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
    """What the wheel has chosen so far: design, accent colour and alarm sign.

    A thread polls the wheel every 30 ms, so a turn registers even while the main loop is busy rendering, and
    shows a ready-made still of the new design at once. The full animation follows once the wheel pauses.
    """
    SETTLE = 0.6  # s without wheel movement before the animation is rendered

    def __init__(self, a, controls):
        self.names = list(DESIGNS)
        self.cycle = a.design == "all"
        self.design = a.design if a.design != "all" else self.names[0]
        self.accent, self.alarm_colour, self.alarm_shape = a.accent, a.alarm_colour, a.alarm_shape
        self.controls, self.changed_at, self.dirty = controls, 0.0, False
        self.swatches = [colour(n) for n in SWATCH]
        self.live = None  # set by main()
        if controls:
            threading.Thread(target=self._watch, daemon=True).start()

    def _watch(self):
        while True:
            time.sleep(0.03)
            steps, clicks = self.controls.take()
            if not (steps or clicks):
                continue
            if steps:
                self.cycle = False
                self.design = self.names[(self.names.index(self.design) + steps) % len(self.names)]
            if clicks:
                if self.design == "alarm":
                    self.alarm_shape = SHAPES[(SHAPES.index(self.alarm_shape) + 1) % len(SHAPES)]
                else:
                    i = self.swatches.index(self.accent) if self.accent in self.swatches else -1
                    self.accent = self.swatches[(i + 1) % len(self.swatches)]
            self.changed_at, self.dirty = time.time(), True
            if self.live:
                self.live.start()

    def settled(self):
        """True once a change is pending and the wheel has paused."""
        return self.dirty and time.time() - self.changed_at >= self.SETTLE


class Live:
    """Streams the chosen design frame by frame while the wheel is being turned.

    Each frame is rendered for the instant it will appear (now + the upload/draw latency), on the same frame grid as
    the pre-rendered minute, so the animation that takes over once the wheel pauses continues exactly where the live
    frames left off. About 9 frames/s: one upload plus one draw per frame.
    """
    LATENCY = 0.1   # s: render for this far ahead of now
    NAMES = 4       # the bar locks the file it shows: rotate filenames

    def __init__(self, base, a, zones, sel):
        self.base, self.a, self.zones, self.sel = base, a, zones, sel
        self.lock = threading.Lock()
        self.active = False       # True from a wheel change until the main loop draws the real animation
        threading.Thread(target=self._run, daemon=True).start()

    def start(self):
        self.active = True

    def stop(self):
        """Called by the main loop, holding self.lock, right before it draws the animation."""
        self.active = False

    def _run(self):
        n = shown = 0
        while True:
            if not self.active:
                time.sleep(0.02)
                continue
            a, sel = self.a, self.sel
            t = time.time() + self.LATENCY
            frame = int(t * a.fps)
            if frame == shown:
                time.sleep(0.01)
                continue
            try:
                rgba = render_at(sel.design if not sel.cycle else sel.names[0], t, a.fps, sel.accent, a.hour12,
                                 not a.steady_colon, self.zones, a.min_alpha, (sel.alarm_colour, sel.alarm_shape))
                name = f"fui_live_{n % self.NAMES}.anim"
                write(ASSETS / name, [rgba], a.fps)
                upload(self.base, name)
                with self.lock:
                    if self.active:  # the main loop may have taken over while this frame was uploading
                        draw(self.base, name, a.priority, time.time() + 0.5)
                n, shown = n + 1, frame
            except Exception as e:  # a dropped frame must never stop the clock
                print(f"live frame failed: {e}", file=sys.stderr, flush=True)
                time.sleep(0.2)


def wait_until(t, sel):
    """Sleep until epoch t; returns True early if the wheel changed something."""
    while (d := t - time.time()) > 0:
        if sel.settled():
            return True
        time.sleep(min(d, 0.05))
    return sel.settled()


def main():
    a = build_parser("FUI Clock: sci-fi HUD clock designs, rendered on the computer").parse_args()
    base = "http://" + a.host.replace("http://", "").rstrip("/")
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    zones, order, fps = parse_zones(a.zones), list(DESIGNS), a.fps
    sel = Selection(a, None if a.no_wheel else Controls(a.host))
    ASSETS.mkdir(exist_ok=True)
    clear(base)
    if sel.controls:
        sel.live = Live(base, a, zones, sel)
    slot, last, switched, playing, resume = 0, None, False, None, None
    try:
        while True:
            now = time.time()
            E0 = int(now // 60) * 60
            lead = FAST if switched else MARGIN
            stop = None
            if resume:  # the quick clip is playing: queue the rest of its minute
                (E, first), resume = resume, None
            elif (last is None or switched) and now - E0 + lead < 56:  # start mid-minute, in step with the seconds
                E, first = E0, int((now - E0 + lead) * fps) + 1
                if switched and first + CLIP * fps < 59 * fps:
                    stop = int(first + CLIP * fps)
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
                                   (sel.alarm_colour, sel.alarm_shape), first=first, last=stop, prev=first == 0)
            slot = (slot + 1) % 3
            if f"fui_clock_{slot}.anim" == playing:  # the bar locks the file it is playing: never overwrite it
                slot = (slot + 1) % 3
            name = f"fui_clock_{slot}.anim"
            write(ASSETS / name, frames, fps)
            try:
                upload(base, name)
            except (urllib.error.URLError, OSError) as e:
                print(f"upload failed, retrying: {e}", file=sys.stderr, flush=True)
                time.sleep(2)
                last = None if last == E else last
                continue
            print(f"{time.strftime('%H:%M', time.localtime(E))} {design}: {len(frames)} frames in {time.time() - t0:.1f}s",
                  flush=True)
            if wait_until(E + first / fps - LEAD, sel):  # the wheel moved while waiting: redo it for the new choice
                switched, last = True, E - 60
                continue
            if sel.dirty:  # the wheel is still moving: do not draw the old design over its preview
                switched, last = True, E - 60
                continue
            switched = False
            if sel.live:
                with sel.live.lock:  # no live frame may land after this draw
                    sel.live.stop()
                    ok = draw(base, name, a.priority, E + 55)
            else:
                ok = draw(base, name, a.priority, E + 55)
            if ok:
                playing = name
            if stop:
                resume = (E, stop)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        clear(base)


if __name__ == "__main__":
    main()
