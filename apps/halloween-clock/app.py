#!/usr/bin/env python3
"""Halloween Clock: orange time over an animated night scene.

    python app.py                              # graveyard scene, 24h clock
    python app.py --style classic              # pumpkin + bat sprites, no random events
    python app.py --hour12 --color "#FF7A00FF"
    python app.py --bat-min 10 --bat-max 30    # bat every 10-30 s (random)
    python app.py --thunder-max 0              # no thunder
    python app.py --weather stormy --moon blood
    python app.py --host 127.0.0.1:8080        # emulator

"graveyard" (default): a looping night scene (tree, pumpkin, tombstones, grass, a soft glow
behind the time) built from stacked layers: a moon (full, half, crescent or blood), a
weather sky and the scenery. Weather: calm (stars, a wisp of cloud), stormy (heavy
clouds, thunder) or foggy (haze and ground mist, rarer thunder). Weather and moon are
picked at random at startup and again every --reroll minutes, unless fixed with
--weather / --moon. Random bat flights (4 variants) cross the bar in every weather.
"classic": pumpkin on the left, bat flapping on the right.

The animations are .anim files in assets/ (see tools/gen_halloween.py and
tools/gen_graveyard.py). They are uploaded once at startup and played by the firmware
itself, so the app only sends a request when the minute changes or an event fires.
"""
import argparse
import base64
import colorsys
import json
import math
import random
import re
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from anim import write_anim

APP = "halloween-clock"
ASSETS = Path(__file__).resolve().parent / "assets"

STYLES = ["graveyard", "classic"]
WEATHERS = ["calm", "stormy", "foggy"]
MOONS = ["full", "half", "crescent", "blood"]
THUNDER_WEATHER = {"stormy": 1.0, "foggy": 2.0}  # thunder only in these; foggy: rarer (x2 waits)


def base_layers(style, weather, moon, night=False):
    """Looping animations, bottom to top: (element id, file, x, y). Night mode (night_*.anim, see
    tools/gen_night.py) is for the lowest bar brightness: opaque pixels only, no mist."""
    if style == "classic":
        return [("pumpkin", "pumpkin.anim", 0, 0), ("bat", "bat.anim", 56, 0)]
    pre = "night_" if night else ""
    layers = [("moon", f"{pre}moon_{moon}.anim", 0, 0), ("sky", f"{pre}sky_{weather}.anim", 0, 0),
              ("moonrim", f"{pre}moonrim_{moon}.anim", 0, 0), ("scenery", f"{pre}scenery.anim", 0, 0)]
    if night:   # the moon sprite has its own outline, so there is no separate rim layer
        layers = [layers[0], layers[1], layers[3]]
    if weather == "foggy" and not night:
        layers.append(("mist", "mist_foggy.anim", 0, 0))
    return layers


BATS = ["bat_lr_high.anim", "bat_rl_high.anim", "bat_lr_low.anim", "bat_rl_low.anim"]
BAT_SECONDS, THUNDER_SECONDS = 3.0, 0.8  # one-shot lengths (frames / 20 fps); element timeouts add
# headroom because the bar needs a moment to load the file and the timeout would cut the end off
CHARGE_SECONDS, CHARGE_FPS = 24.0, 10     # a strike turns the clock green; it fades back to orange



def _color(value):
    value = value.strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}([0-9a-fA-F]{2})?", value):
        raise argparse.ArgumentTypeError("color must be RRGGBB or RRGGBBAA")
    return "#" + (value + "FF" if len(value) == 6 else value).upper()


def args():
    p = argparse.ArgumentParser(description="Halloween clock with an animated night scene")
    p.add_argument("--host", default="10.0.4.20")
    p.add_argument("--style", choices=STYLES, default="graveyard", help="which scene to play")
    p.add_argument("--weather", choices=WEATHERS + ["random"], default="random",
                   help="graveyard weather: calm (stars), stormy (thunder), foggy (thunder) or random")
    p.add_argument("--moon", choices=MOONS + ["random"], default="random", help="moon type, or random")
    p.add_argument("--reroll", type=float, default=60.0,
                   help="minutes between new random weather/moon (only for the ones set to random; 0 = never)")
    p.add_argument("--color", type=_color, default="#FF7A00FF", help="time color, RRGGBB or RRGGBBAA")
    p.add_argument("--hour12", action="store_true", help="12-hour clock instead of 24-hour")
    p.add_argument("--bat-min", type=int, default=20, help="shortest wait between bat flights, seconds")
    p.add_argument("--bat-max", type=int, default=60, help="longest wait between bat flights (0 = no bats)")
    p.add_argument("--thunder-min", type=int, default=30, help="shortest wait between thunderstorms, seconds")
    p.add_argument("--thunder-max", type=int, default=120, help="longest wait between thunderstorms (0 = none)")
    p.add_argument("--refresh", type=float, default=0.0,
                   help="extra full redraws every N seconds (0 = off; the scene is redrawn every minute anyway)")
    p.add_argument("--night", action="store_true",
                   help="night mode for the lowest bar brightness: opaque pixels, few colours, no glow or mist")
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
    for attempt in range(5):  # 508 = asset briefly locked by the display, 408 = slow upload of a big file
        try:
            call(base, "/api/assets/upload?" + q, "POST", raw=data, ctype="application/octet-stream", timeout=60)
            return
        except urllib.error.HTTPError as e:
            if e.code in (408, 508) and attempt < 4:
                time.sleep(0.5 + attempt)
                continue
            raise


def clear(base):
    q = urllib.parse.urlencode({"application_name": APP})
    try:
        call(base, "/api/display/draw?" + q, "DELETE")
    except (urllib.error.URLError, OSError):
        pass


def hex_rgb(value):
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


FLASH, GAP = (170, 255, 190), (0, 110, 12)
GLOW_C, GLOW_HALF, GLOW_ORANGE = (36.0, 7.9), (15.0, 4.4), (255, 100, 0)   # the haze behind the time (see tools/gen_graveyard.py)
GLOW_FPS = 2


def fade_u(t):
    """0 while flashing and holding green, then a smoothstep 0..1 sweeping back to the clock colour."""
    k = t / CHARGE_SECONDS
    if k < 0.2:
        return 0.0
    u = min(1.0, (k - 0.2) / 0.8)
    return u * u * (3 - 2 * u)


def charge_color(t, orange):
    """Colour of the charged clock t seconds after the strike: it flickers with the two bolts (flash,
    gap, flash), holds an electric green, then the hue slowly sweeps green -> yellow -> the clock
    colour (full saturation all the way, so it never goes pale or muddy on the LEDs)."""
    if t < 0.1 or 0.2 <= t < 0.4:
        return FLASH
    if t < 0.2:
        return GAP
    green = 125 / 360
    h0, s0, v0 = colorsys.rgb_to_hsv(*(c / 255 for c in orange))
    u = fade_u(t)
    h, sat, val = green + (h0 - green) * u, 1.0 + (s0 - 1.0) * u, 1.0 + (v0 - 1.0) * u
    return tuple(round(c * 255) for c in colorsys.hsv_to_rgb(h, sat, val))


def glow_level(x, y, f):
    """Strength (0..~0.24) of the glow behind the time at pixel (x, y), animation frame f (20 fps)."""
    breathe = 0.5 + 0.5 * math.sin(2 * math.pi * f / 60 - 1.0)
    dx, dy = max(abs(x - GLOW_C[0]) - GLOW_HALF[0], 0), max(abs(y - GLOW_C[1]) - GLOW_HALF[1], 0)
    return (0.10 + 0.14 * breathe) * math.exp(-((math.hypot(dx, dy) / 3.4) ** 2))


def digit_pixels(base, color):
    """Pixels of the clock digits as drawn on the bar right now (read back from the screen)."""
    raw = urllib.request.urlopen(base + "/api/screen?display=0", timeout=5).read()
    data = base64.b64decode(raw)
    r0, g0, b0 = color
    pts = []
    for y in range(2, 14):
        for x in range(18, 55):
            b, g, r = data[(y * 72 + x) * 3:(y * 72 + x) * 3 + 3]
            if abs(r - r0) < 40 and abs(g - g0) < 40 and abs(b - b0) < 40:
                pts.append((x, y))
    return pts


def charge_element(base, color, n, pts, start=0.0):
    """Upload a fade animation shaped like the digits (pts), starting `start` (0..1) into the fade.
    Returns the element to draw over the time."""
    x0, y0 = min(x for x, _ in pts), min(y for _, y in pts)
    w, h = max(x for x, _ in pts) - x0 + 1, max(y for _, y in pts) - y0 + 1
    total = int(CHARGE_SECONDS * CHARGE_FPS)
    frames = []
    for i in range(int(start * total), total):
        c = tuple(round(v / 6) * 6 for v in charge_color(i / CHARGE_FPS, color))  # steps: repeated frames are free
        buf = bytearray(w * h * 4)
        for x, y in pts:
            o = ((y - y0) * w + (x - x0)) * 4
            buf[o:o + 4] = bytes((c[2], c[1], c[0], 255))  # BGRA
        frames.append(bytes(buf))
    name = f"charge_{n % 2}.anim"  # alternate names so a stale copy is never replayed
    write_anim(ASSETS / name, frames, w, h, CHARGE_FPS)
    upload(base, name)
    return {"id": "charge", "type": "animation", "path": name, "x": x0, "y": y0, "loop": False,
            "timeout": len(frames) / CHARGE_FPS + 2.0}


def glow_element(base, n, start=0.0):
    """The haze behind the time, charged: same shape and breathing as the orange glow in scenery.anim,
    but green, sweeping back to orange together with the digits. Drawn between scenery and time."""
    x0, x1, y0, y1 = 19, 54, 0, 13   # keeps clear of the pumpkin, the tombstones and the grass
    w, h = x1 - x0 + 1, y1 - y0 + 1
    pix = [(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)
           if max(glow_level(x + 0.5, y + 0.5, f) for f in (0, 30)) > 0.02]
    total = int(CHARGE_SECONDS * GLOW_FPS)
    first = int(start * total)
    frames = []
    for i in range(first, total):
        t = i / GLOW_FPS
        c = tuple(round(v / 8) * 8 for v in charge_color(t, GLOW_ORANGE))
        boost = 1.0 + 0.8 * (1.0 - fade_u(t))          # brighter while green, so the colour change shows
        f = (i - first) / GLOW_FPS * 20                  # the breathing restarts with the scene at the redraw
        buf = bytearray(w * h * 4)
        for x, y in pix:
            lvl = glow_level(x + 0.5, y + 0.5, f) * boost
            o = ((y - y0) * w + (x - x0)) * 4
            buf[o:o + 4] = bytes((min(255, round(c[2] * lvl)), min(255, round(c[1] * lvl)),
                                  min(255, round(c[0] * lvl)), 255))
        frames.append(bytes(buf))
    name = f"glowcharge_{n % 2}.anim"
    write_anim(ASSETS / name, frames, w, h, GLOW_FPS)
    upload(base, name)
    return {"id": "glowcharge", "type": "animation", "path": name, "x": x0, "y": y0, "loop": False,
            "timeout": len(frames) / GLOW_FPS + 2.0}


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
    bats = ["night_" + b for b in BATS] if a.night else BATS
    thunder_file = "night_thunder.anim" if a.night else "thunder.anim"

    def time_element(text, color=None):
        return {"id": "time", "type": "text", "text": text, "font": "extra_large",
                "color": color or a.color, "x": 36, "y": 8, "align": "center"}

    def scene_elements(text, glow=None, color=None):
        """Every element, bottom to top. A draw replaces what we had; elements sent alone end up
        behind the others, so events are always sent together with the whole scene. The charged
        glow, when there is one, goes between the scenery and the time."""
        return ([{"id": eid, "type": "animation", "path": f, "x": x, "y": y, "loop": True}
                 for eid, f, x, y in base_layers(a.style, weather, moon, a.night)]
                + ([glow] if glow else []) + [time_element(text, color)])

    def send(elements):
        call(base, "/api/display/draw", "POST",
             {"application_name": APP, "priority": a.priority, "elements": elements})

    base_drawn, shown = False, None
    last_full, hour_strike_at, charges = 0.0, None, 0
    charge_pts, charge_start, charge_text = None, 0.0, None   # the clock charged by lightning, fading to orange

    def charge_overlay(fresh=False):
        """The charge in progress (digits and glow elements), resumed at its current point, or from
        the start for a new strike; None when it is over."""
        nonlocal charges
        remaining = CHARGE_SECONDS if fresh else charge_start + CHARGE_SECONDS - time.monotonic()
        if not charge_pts or remaining < 1.0:
            return None
        charges += 1
        start = 1 - remaining / CHARGE_SECONDS
        return {"digits": charge_element(base, hex_rgb(a.color), charges, charge_pts, start),
                "glow": None if a.night else glow_element(base, charges, start)}

    next_bat = next_thunder = None
    uploaded, rolled = set(), None   # files already on the bar; when the weather was last rolled
    weather, moon, picked = None, None, False

    def roll():
        """Pick the weather and moon (random unless fixed on the command line)."""
        nonlocal weather, moon, next_bat, next_thunder, base_drawn, picked
        if not picked:  # a failed upload is retried with the same pick
            weather = random.choice(WEATHERS) if a.weather == "random" else a.weather
            moon = random.choice(MOONS) if a.moon == "random" else a.moon
            picked = True
            print(f"weather: {weather}, moon: {moon}", flush=True)
        files = [f for _, f, _, _ in base_layers(a.style, weather, moon, a.night)]
        if events_on:
            files += bats + ([thunder_file] if weather in THUNDER_WEATHER else [])
        for name in files:
            if name not in uploaded:
                upload(base, name)
                uploaded.add(name)
        if events_on:
            wait = THUNDER_WEATHER.get(weather)
            next_bat = schedule(a.bat_min, a.bat_max)
            next_thunder = schedule(a.thunder_min * wait, a.thunder_max * wait) if wait else None
        picked = False
        clear(base)  # the new layers replace the old ones (a mist layer may have to go)
        base_drawn = False

    # On Windows the manager stops apps with a hard kill, so the cleanup in `finally`
    # may never run. Wipe whatever a previous run (or style) left on the bar.
    clear(base)
    try:
        while True:
            try:
                reroll = (events_on and a.reroll > 0 and "random" in (a.weather, a.moon)
                          and rolled is not None and time.monotonic() - rolled >= a.reroll * 60)
                if rolled is None or reroll:
                    roll()
                    rolled = time.monotonic()
                # The bar has no read-back of what is on screen, so if another app replaced
                # us we can't tell. Periodically redraw everything to recover.
                if base_drawn and a.refresh > 0 and time.monotonic() - last_full >= a.refresh:
                    base_drawn = False
                text = clock_text(time.localtime(), a.hour12)
                # Updating only the time text makes the bar stop rendering it once the scene has
                # heavy animations, so every minute change redraws all elements. The loops are
                # 60 s / n long and restart together, so that redraw causes no visible jump.
                if text != shown:
                    base_drawn = False
                    if shown and text.endswith(":00") and weather in THUNDER_WEATHER and events_on:
                        hour_strike_at = time.monotonic() + 1.5  # a new hour: lightning charges the clock
                if not base_drawn:
                    fading = charge_pts and charge_start + CHARGE_SECONDS - time.monotonic() > 1.0
                    cur = None
                    if fading:
                        # The digits are redrawn in the colour the fade has reached, not in orange:
                        # otherwise they would flash orange until the new overlay is uploaded.
                        cur = charge_color(time.monotonic() - charge_start, hex_rgb(a.color))
                    send(scene_elements(text, color="#%02X%02X%02XFF" % cur if cur else None))
                    if fading:
                        # A fade is still running but the digits changed: read their new shape
                        # and carry on with the fade where it was.
                        time.sleep(0.4)
                        charge_pts, charge_text = digit_pixels(base, cur), text
                        ov = charge_overlay() if len(charge_pts) >= 20 else None
                        if ov:
                            send(scene_elements(text, ov["glow"]) + [ov["digits"]])
                    base_drawn, shown, last_full = True, text, time.monotonic()

                # Random one-shot events, drawn over the scene (and over the time while they last).
                now = time.monotonic()
                if events_on and base_drawn:
                    fired, extra = [], []
                    if next_bat and now >= next_bat:
                        fired.append({"id": "bat", "type": "animation", "path": random.choice(bats),
                                      "x": 0, "y": 0, "loop": False, "timeout": BAT_SECONDS + 2.0})
                        next_bat = schedule(a.bat_min, a.bat_max)
                    strike = False
                    if hour_strike_at and now >= hour_strike_at:
                        strike, hour_strike_at = True, None
                    elif next_thunder and now >= next_thunder:
                        strike = True
                    if strike:
                        wait = THUNDER_WEATHER[weather]
                        next_thunder = schedule(a.thunder_min * wait, a.thunder_max * wait)
                        fired.append({"id": "thunder", "type": "animation", "path": thunder_file,
                                      "x": 0, "y": 0, "loop": False, "timeout": THUNDER_SECONDS + 1.5})
                        pts = digit_pixels(base, hex_rgb(a.color))  # the strike charges the clock
                        print(f"{time.strftime('%H:%M:%S')} strike ({weather}), digit pixels: {len(pts)}", flush=True)
                        if len(pts) >= 20:
                            charge_pts, charge_start, charge_text = pts, time.monotonic(), shown
                        elif charge_pts and charge_text == shown:
                            charge_start = time.monotonic()   # struck again while still charged: recharge
                    glow = None
                    if fired:
                        if charge_pts and charge_text == shown:
                            # bats and strikes redraw the scene: a new strike starts the fade, a bat
                            # keeps the running one going
                            ov = charge_overlay(fresh=strike)
                            if ov:
                                extra.append(ov["digits"])
                                glow = ov["glow"]
                        # Redrawn with the scene so the bat flies in front of the time, a bit of
                        # parallax. The loops restart, which is hardly noticeable.
                        send(scene_elements(shown, glow) + extra + fired)
                        last_full = time.monotonic()
            except urllib.error.HTTPError as e:
                base_drawn = False  # force a full redraw once we get the screen back
                if e.code == 409:
                    print("draw rejected (409): another app holds the screen", flush=True)
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
