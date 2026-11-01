"""Scenes: compositions of widgets, each with a loop length and parameters.

OPTIONS is the shared vocabulary of parameters (name -> type, default, help). A scene lists the options it
reads and may override their defaults. app.py turns this into command-line flags, which the manager shows as
form controls, so every number here is tunable from the dashboard.
"""
import math

from . import widgets as w
from .canvas import GREEN, H, RED, W, WHITE, noise, rnd, text_width

TAU = 2 * math.pi

OPTIONS = {
    "cycles": (int, 3, "motion repeats per loop (wave periods, scan passes): higher = faster"),
    "amplitude": (float, 3.4, "wave height in pixels"),
    "thickness": (int, 1, "line thickness in pixels"),
    "fade": (float, 0.8, "how much the old end of a trace dims, 0 = not at all, 1 = fully"),
    "value": (float, -1.0, "fixed value 0-100; -1 = animate by itself"),
    "segments": (int, 17, "number of gauge segments"),
    "warn_from": (int, 13, "first gauge segment drawn in the warning colour"),
    "trail": (int, 12, "length of the beam's fading trail in pixels"),
    "bars": (int, 8, "number of bars in the bar chart"),
    "label": (str, "", "caption text (capitals, digits and - : . % /); empty = the scene's own"),
}


def _value(p, ph, base=0.5, swing=0.38, ripple=0.08):
    """0..1 reading: the fixed --value, or a smooth animated one that loops seamlessly."""
    if p["value"] >= 0:
        return min(1.0, p["value"] / 100.0)
    return max(0.0, min(1.0, base + swing * math.sin(TAU * ph) + ripple * math.sin(TAU * 24 * ph)))


def scope(c, ph, p, acc):
    w.baseline(c, acc, 9, 0.3)
    w.ruler(c, acc, 15, 6, 0.6)
    w.wave(c, ph, acc, amp=p["amplitude"], cycles=p["cycles"], thickness=p["thickness"], fade=p["fade"])
    c.text(p["label"] or "SIG", 2, 0, acc, 1, 0.7)
    c.text(str(rnd(440 + 20 * math.sin(TAU * ph))) + "HZ", 52, 0, acc, 1, 0.7)


def gauge(c, ph, p, acc):
    v = _value(p, ph)
    peak = None if p["value"] >= 0 else 0.5 + 0.46 * math.sin(TAU * ph - 0.5)
    lit = rnd(v * p["segments"])
    c.text(p["label"] or "PWR", 2, 1, acc, 1, 0.7)
    s = str(rnd(v * 100)) + "%"
    c.text(s, 70 - text_width(s), 1, RED if lit >= p["warn_from"] + 1 else acc)
    seg_w = max(1, (W - 4 - (p["segments"] - 1)) // p["segments"])
    w.gauge(c, v, acc, x=2, y=8, seg_w=seg_w, segments=p["segments"], warn_from=p["warn_from"], peak=peak)


def telemetry(c, ph, p, acc):
    t = ph * 4000
    alt = 12000 + int(noise(int(t // 660)) * 900)
    vel = 300 + int(noise(int(t // 660) + 7) * 90)
    w.readout(c, "ALT", str(alt), 2, 2, acc, 0.6)
    w.readout(c, "VEL", str(vel).rjust(4, "0"), 2, 9, acc, 0.6)
    for y in range(1, 15, 2):
        c.px(40, y, acc, 0.4)
    prev = -1
    for i in range(27):
        x = 43 + i
        y = rnd(8 + p["amplitude"] * 0.94 * math.sin(i * 0.45 + TAU * ph) + 1.6 * math.sin(i * 1.1 + TAU * 4 * ph))
        a = 0.55 + 0.45 * i / 27
        for yy in range(y, 15):
            c.px(x, yy, acc, 0.12 + 0.12 * i / 27)
        for yy in range(min(prev if prev >= 0 else y, y), max(prev if prev >= 0 else y, y) + 1):
            c.px(x, yy, acc, a)
        prev = y
    c.px(69, prev, WHITE, 1)


def scanner(c, ph, p, acc):
    w.dot_grid(c, acc, 0.22)
    sx = w.scanline(c, (ph * p["cycles"]) % 1.0, acc, trail=p["trail"])
    near = abs(sx - 36) < 4
    w.reticle(c, 36, 8, acc, 0.85, near)
    c.text(p["label"] or "SCAN", 2, 1, acc, 1, 0.7)
    c.text("T-" + str(int(ph * 6)).rjust(2, "0"), 54, 1, acc, 1, 0.6)
    if near or int(ph * 6000 // 330) % 4 == 0:
        c.text("LOCK", 50, 10, WHITE, 1, 1 if near else 0.55)


def stream(c, ph, p, acc):
    t = ph * 7500
    w.hexstream(c, ph, acc, 0, 1, 0.34)
    w.hexstream(c, ph, acc, 11, 99, 0.34, direction=-1)
    ok = int(t // 2500) % 2 == 1
    msg = p["label"] or ("ACCESS GRANTED" if ok else "AUTHENTICATING")
    if p["label"]:
        ok = False
    w.banner(c, msg, GREEN if ok else acc, 1 if ok else 0.6 + 0.4 * math.sin(TAU * 10 * ph))
    if not ok:
        step = int(((t % 2500) / 2500) * 14)
        for i in range(14):
            c.px(11 + i * 3, 4, acc, 0.85 if i <= step else 0.25)


def brackets(c, ph, p, acc):
    t = ph * 6000
    w.brackets(c, acc, 0.9)
    v = rnd(30 + noise(int(t // 1000)) * 65) if p["value"] < 0 else rnd(p["value"])
    c.text(p["label"] or "CPU", 5, 3, acc, 1, 0.7)
    c.text("LOAD", 5, 9, acc, 1, 0.4)
    s = str(v)
    c.text(s, 24, 3, acc, 2)
    c.text("%", 24 + text_width(s, 2) + 2, 3, acc, 1, 0.7)
    n = p["bars"]
    w.bars(c, int(t // 330), acc, x=44, n=n, bar_w=2 if n <= 8 else 1, gap=1)
    for x in range(5, 67, 3):
        c.px(x, 14, acc, 0.3)
    m = 5 + int(ph * 62)
    c.px(m, 14, WHITE, 1)
    c.px(m, 13, acc, 0.8)


def alert(c, ph, p, acc):
    a = 0.6 + 0.4 * math.sin(TAU * ph)
    w.hazard(c, int(ph * 2000 // 125), RED, 0.8)
    w.warn_triangle(c, 9, 3, RED, a)
    c.text(p["label"] or "WARN", 18, 4, RED, 2, a)
    c.text("E-07", 54, 4, RED, 1, 0.85)
    c.text("TEMP", 54, 10, RED, 1, 0.5)


SCENES = {
    "scope": dict(draw=scope, loop=7.5, opts=["cycles", "amplitude", "thickness", "fade", "label"]),
    "gauge": dict(draw=gauge, loop=8.0, opts=["value", "segments", "warn_from", "label"]),
    "telemetry": dict(draw=telemetry, loop=4.0, opts=["amplitude"], defaults={"amplitude": 3.4}),
    "scanner": dict(draw=scanner, loop=6.0, opts=["cycles", "trail", "label"], defaults={"cycles": 1}),
    "stream": dict(draw=stream, loop=7.5, opts=["label"]),
    "brackets": dict(draw=brackets, loop=6.0, opts=["value", "bars", "label"]),
    "alert": dict(draw=alert, loop=2.0, opts=["label"], red=True),
}
