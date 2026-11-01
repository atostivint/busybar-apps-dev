"""Clock designs. Each is draw(c, x) with x a Ctx; DESIGNS maps name -> (draw, description, options).

Everything is a function of time, so a minute can be rendered ahead and played by the firmware:
  x.T  absolute epoch seconds (ambient motion uses it, so it continues across minutes)
  x.t  seconds since the minute began (0..60): the seconds hand, progress lines
  x.s  whole second, x.hh / x.mm the minute's time, x.prev the previous minute's (hh, mm) or None
"""
import math
import time

from . import widgets as w
from .canvas import GREEN, H, RED, W, WHITE, noise, rnd, text_width
from .fonts import Bitmap, Dots, Seg, layout, put

TAU = 2 * math.pi

THIN2 = Bitmap(2)
THIN1 = Bitmap(1)
SEG_SOLID = Seg(8, 11, 2)
SEG_THIN = Seg(7, 13, 1)
SEG_ITALIC = Seg(7, 11, 2, slant=3)
SEG_MONO = Seg(10, 16, 3)
DOTS2 = Dots(2)
DAYS = "MTWTFSS"


class Ctx:
    def __init__(self, T, t, hh, mm, prev, date, acc, hour12=False, blink=True, zones=(), alarm=(RED, "triangle")):
        self.T, self.t, self.s = T, t, int(t)
        self.hh, self.mm, self.prev, self.date = hh, mm, prev, date
        self.acc, self.hour12, self.blink, self.zones = acc, hour12, blink, zones
        self.alarm_colour, self.alarm_shape = alarm

    def hour(self, hh=None):
        hh = self.hh if hh is None else hh
        return (hh % 12 or 12) if self.hour12 else hh

    def text(self, hh=None, mm=None):
        return f"{self.hour(hh):02d}:{self.mm if mm is None else mm:02d}"

    @property
    def colon(self):
        """Colon brightness: steady, or blinking once a second."""
        return 1.0 if not self.blink or (self.t % 1.0) < 0.5 else 0.12


def draw_time(c, x, font, y, s=None, at=None, gap=1, a_on=1.0, a_off=0.0, color=None, dx=0):
    """Draw the time (or `s`) with the colon honouring the blink; centred unless `at` is given. Returns (x0, x1)."""
    items, width = layout(font, s or x.text(), gap)
    x0 = at if at is not None else (W - width) // 2
    color = color or x.acc
    for ch, ox, px in items:
        if ch == ":":
            put(c, px, x0 + ox + dx, y, color, a_on * x.colon, 0)
        else:
            put(c, px, x0 + ox + dx, y, color, a_on, a_off)
    return x0, x0 + width


def sec_line(c, x, y, x0=6, n=60, a_lit=0.9, a_dim=0.25, marks=True):
    """60 ticks, one per second: lit up to now with a bright head (smooth within the second)."""
    for i in range(n):
        c.px(x0 + i, y, x.acc, a_lit if i < x.s else a_dim)
    c.px(x0 + x.s, y, WHITE, 0.4 + 0.6 * (1 - (x.t % 1.0)))
    if marks:
        for i in range(0, n, 15):
            c.px(x0 + i, y + 1, x.acc, 0.6)


# ----------------------------------------------------------------------------------------------------- designs

def seg(c, x):
    draw_time(c, x, SEG_SOLID, 1, gap=2, a_off=0.14)
    sec_line(c, x, 14)


def thin(c, x):
    x0, x1 = draw_time(c, x, SEG_THIN, 1, gap=4)
    for xx in (x0 - 7, x1 + 6):
        for y in range(1, 14):
            c.px(xx, y, x.acc, 0.35)
    p = (x.t / 60.0) * 13
    for k in range(13):
        a = 1.0 if int(p) == k else (0.55 if k < p else 0.2)
        c.px(x0 - 7, 13 - k, x.acc, a)
        c.px(x1 + 6, 1 + k, x.acc, a)
    for k in range(0, 13, 3):
        c.px(x0 - 8, 13 - k, x.acc, 0.5)
        c.px(x1 + 7, 1 + k, x.acc, 0.5)


def matrix(c, x):
    x0, x1 = draw_time(c, x, DOTS2, 1, gap=3, a_off=0.1)
    sx = x0 - 6 + (x1 - x0 + 12) * (x.t % 1.0)
    items, _ = layout(DOTS2, x.text(), 3)  # a bright scan column sweeps once a second
    for ch, ox, px in items:
        for (gx, gy, on) in px:
            if on and abs(x0 + ox + gx - sx) < 1.6 and not (ch == ":" and x.colon < 0.5):
                c.px(x0 + ox + gx, 1 + gy, WHITE, 1)
    for i in range(0, W, 2):
        c.px(i, 15, x.acc, 0.18)
    c.px(2 * int(x.t % 36), 15, x.acc, 0.9)


def _perimeter():
    pts = [(xx, 0) for xx in range(36, 72)] + [(71, yy) for yy in range(1, 16)]
    pts += [(xx, 15) for xx in range(70, -1, -1)] + [(0, yy) for yy in range(14, 0, -1)]
    pts += [(xx, 0) for xx in range(0, 36)]
    return pts


PERIM = _perimeter()


def perimeter(c, x):
    p = x.t / 60.0 * len(PERIM)
    for i, (px, py) in enumerate(PERIM):
        if i < p - 1:
            a = 0.5
        elif i <= p:
            a = 1.0
        else:
            a = 0.13
        c.px(px, py, x.acc, a)
    hx, hy = PERIM[min(len(PERIM) - 1, int(p))]
    c.px(hx, hy, WHITE, 1)
    for k in range(0, 60, 5):  # a brighter pip every five seconds
        px, py = PERIM[int(k / 60.0 * len(PERIM))]
        if int(k / 60.0 * len(PERIM)) > p:
            c.px(px, py, x.acc, 0.6)
    draw_time(c, x, THIN2, 3, gap=2)


def radar(c, x):
    cx, cy, r = 8, 8, 7
    for k in range(24):
        a = TAU * k / 24
        c.px(cx + r * math.cos(a), cy + r * math.sin(a), x.acc, 0.85 if k % 6 == 0 else 0.3)
    ang = TAU * x.t / 60 - math.pi / 2
    for k in range(1, 22):  # fading sweep wedge behind the hand
        a = ang - k * 0.045
        al = (1 - k / 22) ** 2 * 0.55
        for rr in (2, 3, 4, 5, 6):
            c.px(cx + rr * math.cos(a), cy + rr * math.sin(a), x.acc, al)
    c.line(cx, cy, cx + 6 * math.cos(ang), cy + 6 * math.sin(ang), WHITE, 1)
    mang = TAU * (x.mm + x.t / 60) / 60 - math.pi / 2
    hang = TAU * ((x.hh % 12) + x.mm / 60) / 12 - math.pi / 2
    c.line(cx, cy, cx + 5 * math.cos(mang), cy + 5 * math.sin(mang), x.acc, 0.95)
    c.line(cx, cy, cx + 3 * math.cos(hang), cy + 3 * math.sin(hang), x.acc, 0.95)
    c.px(cx, cy, WHITE, 1)
    for yy in range(1, 15, 2):
        c.px(19, yy, x.acc, 0.35)
    draw_time(c, x, THIN2, 3, at=23, gap=2)
    c.text(f"{x.s:02d}", 62, 6, x.acc, 1, 0.8)
    for k in range(0, 60, 5):
        c.px(60, 1 + k // 5, x.acc, 0.7 if k <= x.s else 0.25)


def binary(c, x):
    cols = [x.hour() // 10, x.hour() % 10, x.mm // 10, x.mm % 10, x.s // 10, x.s % 10]
    bits = [2, 4, 3, 4, 3, 4]
    x0 = 2
    for i, (v, nb) in enumerate(zip(cols, bits)):
        cx = x0 + i * 4 + (i // 2) * 2
        for b in range(4):
            bit = 3 - b
            if bit >= nb:
                continue
            lit = (v >> bit) & 1
            c.rect(cx, 1 + b * 4, 2, 2, x.acc if i < 4 else WHITE, 1.0 if lit else 0.16)
    x1 = x0 + 5 * 4 + 2 * 2 + 2
    for yy in range(0, 16, 2):
        c.px(x1 + 3, yy, x.acc, 0.3)
    draw_time(c, x, THIN2, 3, at=37, gap=2)


def brackets(c, x):
    arm = 4 if (x.t % 1.0) < 0.12 else 3
    w.brackets(c, x.acc, 0.95, arm=arm)
    draw_time(c, x, THIN2, 3, gap=2)
    c.text("SYS", 3, 3, x.acc, 1, 0.65)
    c.text("CLK", 3, 9, x.acc, 1, 0.35)
    c.text(f"{x.s:02d}", 59, 3, x.acc, 1, 0.9)
    c.text("SEC", 56, 9, x.acc, 1, 0.35)
    for xx in range(5, 67, 3):
        c.px(xx, 14, x.acc, 0.3)
    m = 5 + int(x.t / 60 * 62)
    c.px(m, 14, WHITE, 1)
    c.px(m, 13, x.acc, 0.8)


_EKG = [0, 0, 0, 0, 0, 0, -1, -1.5, -1, 0, 1, -5, 3, 0, 0, 0, -1, -2, -2, -1, 0, 0, 0, 0]


def pulse(c, x):
    shift = int(x.T * 24)  # 24 px a second = one beat a second
    prev = None
    for xx in range(W):
        y = rnd(8 + _EKG[(xx + shift) % 24] * 1.3)
        a = 0.25 + 0.55 * xx / W
        lo, hi = (y, y) if prev is None else (min(prev, y), max(prev, y))
        for yy in range(lo, hi + 1):
            c.px(xx, yy, x.acc, a)
        prev = y
    x0, x1 = draw_time(c, x, THIN2, 3, gap=2, a_on=0.0)
    c.shade(x0 - 2, 2, x1 - x0 + 4, 12, 0.9)
    draw_time(c, x, THIN2, 3, gap=2)


def telemetry(c, x):
    c.text("SYS CLK", 2, 0, x.acc, 1, 0.55)
    d = f"{x.date.tm_mday:02d}.{x.date.tm_mon:02d}"
    c.text(d, 70 - text_width(d), 0, x.acc, 1, 0.55)
    draw_time(c, x, THIN2, 6, at=2, gap=2)
    c.text(f"{x.s:02d}", 41, 6, x.acc, 2, 0.6)
    w.bars(c, int(x.T * 4), x.acc, x=58, base=15, n=4, bar_w=2, gap=1, max_h=9)
    for xx in range(2, 70, 2):
        c.px(xx, 5, x.acc, 0.15)


def glitch(c, x):
    k = int(x.T * 20)
    burst = noise(int(x.T) * 7.1) > 0.68 and (x.T % 1.0) < 0.4
    items, width = layout(SEG_SOLID, x.text(), 2)
    x0 = (W - width) // 2
    rows = {}
    for ch, ox, px in items:
        for gx, gy, on in px:
            if on and not (ch == ":" and x.colon < 0.5):
                rows.setdefault(gy, []).append(x0 + ox + gx)
    for gy, xs in rows.items():
        off = 0
        if burst and noise(gy * 3.7 + k) > 0.55:
            off = rnd((noise(gy + k * 1.3) - 0.5) * 9)
        dim = 0.75 if gy % 2 else 1.0
        for xx in xs:
            if burst:
                c.px(xx + off + 2, 2 + gy, WHITE, 0.35)
            c.px(xx + off, 2 + gy, x.acc, dim)
    if burst:
        for i in range(10):
            c.px(noise(k + i) * W, noise(k + i * 5 + 3) * H, x.acc, 0.5 + 0.5 * noise(k + i * 9))
        by = rnd(noise(k) * 12) + 1
        for xx in range(W):
            if noise(xx + k) > 0.45:
                c.px(xx, by, WHITE, 0.4)
    sec_line(c, x, 15, marks=False)


def holo(c, x):
    items, width = layout(SEG_SOLID, x.text(), 2)
    x0 = (W - width) // 2
    bx = x0 - 10 + (width + 20) * (x.T % 1.0)
    for ch, ox, px in items:
        for gx, gy, on in px:
            if not on or (ch == ":" and x.colon < 0.5):
                continue
            d = bx - (x0 + ox + gx)
            a = 0.3 + 0.7 * max(0.0, 1 - d / 16) if d >= 0 else 0.3
            c.px(x0 + ox + gx, 2 + gy, x.acc, a)
    for k in range(10):
        c.line(bx - k, 0, bx - k, 15, x.acc, (1 - k / 10) ** 2 * 0.5)
    c.line(bx, 0, bx, 15, WHITE, 0.9)
    for xx in range(0, W, 3):
        c.px(xx, 0, x.acc, 0.3)
        c.px(xx, 15, x.acc, 0.3)


def hexbg(c, x):
    w.hexstream(c, (x.T / 12.0) % 1.0, x.acc, 0, 3, 0.3)
    w.hexstream(c, (x.T / 12.0) % 1.0, x.acc, 11, 41, 0.3, direction=-1)
    items, width = layout(THIN2, x.text(), 2)
    x0 = (W - width) // 2
    c.shade(x0 - 3, 3, width + 6, 10, 0.92)
    draw_time(c, x, THIN2, 3, gap=2)
    c.px(x0 - 3, 3, x.acc, 0.8)
    c.px(x0 - 3, 12, x.acc, 0.8)
    c.px(x0 + width + 2, 3, x.acc, 0.8)
    c.px(x0 + width + 2, 12, x.acc, 0.8)


def bars3(c, x):
    rows = (("H", (x.hh + x.mm / 60) / 24, f"{x.hour():02d}"),
            ("M", (x.mm + x.t / 60) / 60, f"{x.mm:02d}"),
            ("S", x.t / 60, f"{x.s:02d}"))
    for i, (lab, frac, val) in enumerate(rows):
        y = i * 5 + 1
        c.text(lab, 2, y, x.acc, 1, 0.7)
        lit = frac * 48
        for k in range(48):
            if k % 2 == 0:
                a = 1.0 if k + 1 < lit else (0.5 if k < lit else 0.17)
                for yy in range(3):
                    c.px(8 + k, y + 1 + yy, x.acc, a)
        c.px(8 + int(lit), y, WHITE, 0.9)
        c.text(val, 62, y, x.acc, 1, 0.95)


def arc(c, x):
    cx, cy = 8, 8
    frac = x.t / 60
    for yy in range(16):
        for xx in range(16):
            dx, dy = xx - cx, yy - cy
            d = math.hypot(dx, dy)
            if d > 7.3:
                continue
            ang = (math.atan2(dx, -dy) % TAU) / TAU
            if d >= 6.3:
                c.px(xx, yy, x.acc, 0.95 if ang <= frac else 0.35)
            elif d > 1.2:
                c.px(xx, yy, x.acc, 0.55 if ang <= frac else 0.12)
    c.px(cx, cy, WHITE, 1)
    draw_time(c, x, THIN2, 3, at=24, gap=2)
    c.text("SEC", 61, 3, x.acc, 1, 0.5)
    c.text(f"{x.s:02d}", 63, 9, x.acc, 1, 0.95)


def odometer(c, x):
    ease = 1.0
    if x.prev is not None and x.t < 0.9:
        u = x.t / 0.9
        ease = 1 - (1 - u) ** 3
    cur = x.text()
    old = x.text(*x.prev) if x.prev is not None else cur
    items, width = layout(THIN2, cur, 2)
    old_items, _ = layout(THIN2, old, 2)
    x0 = (W - width) // 2
    c.clip = (0, 3, W, 13)
    for (ch, ox, px), (och, _, opx) in zip(items, old_items):
        if ch == ":":
            put(c, px, x0 + ox, 3, x.acc, x.colon, 0)
        elif ch == och or ease >= 1.0:
            put(c, px, x0 + ox, 3, x.acc)
        else:
            put(c, opx, x0 + ox, 3 - ease * 12, x.acc, 0.8)
            put(c, px, x0 + ox, 3 + 12 - ease * 12, x.acc)
    c.clip = (0, 0, W, H)
    for xx in range(0, W, 2):
        c.px(xx, 1, x.acc, 0.25)
        c.px(xx, 14, x.acc, 0.25)
    for k in range(3):
        c.px(2 + k, 7 + k, x.acc, 0.8)
        c.px(2 + k, 8 + (2 - k) + 0, x.acc, 0.8)
        c.px(69 - k, 7 + k, x.acc, 0.8)
        c.px(69 - k, 8 + (2 - k), x.acc, 0.8)
    sec_line(c, x, 15, marks=False)


def tape(c, x):
    draw_time(c, x, THIN2, 1, gap=2)
    off = int(x.T * 4)
    for xx in range(W):
        u = xx + off
        a = 0.95 * (1 - abs(xx - 36) / 40)
        if u % 20 == 0:
            for yy in range(12, 16):
                c.px(xx, yy, x.acc, a)
        elif u % 4 == 0:
            for yy in range(14, 16):
                c.px(xx, yy, x.acc, a * 0.8)
    c.px(36, 11, WHITE, 1)
    c.px(35, 10, WHITE, 0.7)
    c.px(37, 10, WHITE, 0.7)
    c.px(36, 12, WHITE, 1)


def rain(c, x):
    for i in range(24):
        col = 1 + i * 3
        speed = 5 + 11 * noise(i)
        head = (x.T * speed + noise(i + 50) * 40) % 36 - 10
        for k in range(8):
            yy = rnd(head) - k
            if 0 <= yy < H:
                c.px(col, yy, WHITE if k == 0 else x.acc, 0.8 if k == 0 else (1 - k / 8) * 0.55)
    items, width = layout(THIN2, x.text(), 2)
    x0 = (W - width) // 2
    c.shade(x0 - 3, 2, width + 6, 12, 0.93)
    draw_time(c, x, THIN2, 3, gap=2)


def target(c, x):
    cx, cy = 9, 8
    hot = int(x.t) % 10 == 0 and (x.t % 1.0) < 0.5
    w.reticle(c, cx, cy, x.acc, 0.85, hot)
    for k in range(4):
        a = TAU * (x.t / 6.0 + k / 4.0)
        c.px(cx + 4.4 * math.cos(a), cy + 4.4 * math.sin(a), WHITE, 0.9)
    if hot:
        c.text("LOCK", 52, 12, WHITE, 1, 0.9)
    else:
        c.text("TRK", 55, 12, x.acc, 1, 0.4)
    draw_time(c, x, THIN2, 2, at=24, gap=2)
    for xx in range(24, 58, 2):
        c.px(xx, 13, x.acc, 0.2)
    c.px(24 + int(x.t / 60 * 33), 13, WHITE, 1)


SHAPES = ("triangle", "circle", "octagon", "diamond", "bolt")


def _bang(c, cx, top, colour, a):
    for y in range(top, top + 4):
        c.px(cx, y, colour, a)
    c.px(cx, top + 5, colour, a)


def warning_shape(c, kind, cx, colour, a):
    """A 10-row warning sign centred on column cx, rows 3-12."""
    if kind == "triangle":
        w.warn_triangle(c, cx, 3, colour, a)
    elif kind == "circle":
        for k in range(40):
            ang = TAU * k / 40
            c.px(cx + 5 * math.cos(ang), 8 + 5 * math.sin(ang), colour, a)
        _bang(c, cx, 5, colour, a)
    elif kind == "octagon":
        pts = [(cx - 2, 3), (cx + 2, 3), (cx + 5, 6), (cx + 5, 9), (cx + 2, 12), (cx - 2, 12), (cx - 5, 9), (cx - 5, 6), (cx - 2, 3)]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            c.line(x0, y0, x1, y1, colour, a)
        _bang(c, cx, 5, colour, a)
    elif kind == "diamond":
        pts = [(cx, 3), (cx + 5, 8), (cx, 13), (cx - 5, 8), (cx, 3)]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            c.line(x0, y0, x1, y1, colour, a)
        _bang(c, cx, 6, colour, a)
    else:  # bolt
        for off in (0, 1):
            c.line(cx + 3 + off, 3, cx - 2 + off, 8, colour, a)
            c.line(cx - 2 + off, 8, cx + 2 + off, 8, colour, a)
            c.line(cx + 2 + off, 8, cx - 3 + off, 13, colour, a)


def alarm(c, x):
    col = x.alarm_colour
    w.hazard(c, int(x.T * 8), col, 0.85)
    blink = 0.55 + 0.45 * math.sin(TAU * x.T)
    warning_shape(c, x.alarm_shape, 9, col, blink)
    draw_time(c, x, THIN2, 3, at=19, gap=2, color=col)
    c.text("CLK", 57, 4, col, 1, 0.85)
    c.text("ERR", 57, 9, col, 1, 0.45 + 0.4 * (int(x.T * 2) % 2))


def monolith(c, x):
    draw_time(c, x, SEG_MONO, 0, gap=2, a_off=0.1)
    lit = x.t / 60 * 16
    mlit = (x.mm + x.t / 60) / 60 * 16
    for k in range(16):
        for xx in (0, 1):
            c.px(xx, 15 - k, x.acc, 1.0 if k + 1 <= lit else (0.55 if k < lit else 0.15))
            c.px(70 + xx, 15 - k, x.acc, 1.0 if k + 1 <= mlit else (0.55 if k < mlit else 0.15))


def warp(c, x):
    for i in range(16):
        y = rnd(noise(i * 3.1) * 15)
        speed = 18 + 70 * noise(i + 9)
        length = 4 + int(10 * noise(i + 30))
        head = W - (x.T * speed + noise(i + 70) * 200) % (W + length + 6) + 3
        for k in range(length):
            c.px(head + k, y, x.acc, (1 - k / length) * 0.5)
    items, width = layout(SEG_ITALIC, x.text(), 2)
    x0 = (W - width) // 2
    c.shade(x0 - 3, 1, width + 6, 14, 0.92)
    draw_time(c, x, SEG_ITALIC, 2, gap=2, a_off=0.0)


def _zone_time(name, x):
    if name == "LOC":
        return x.hh, x.mm
    try:
        from zoneinfo import ZoneInfo
        from datetime import datetime
        if name == "UTC":
            lt = time.gmtime(x.T - x.t)
            return lt.tm_hour, lt.tm_min
        dt = datetime.fromtimestamp(x.T - x.t, ZoneInfo(name))
        return dt.hour, dt.minute
    except Exception:
        lt = time.gmtime(x.T - x.t)
        return lt.tm_hour, lt.tm_min


def world(c, x):
    cells = [("LOC", "LOC")] + list(x.zones[:3])
    for i, (label, zone) in enumerate(cells):
        cx, cy = 2 + (i % 2) * 37, 1 + (i // 2) * 7
        hh, mm = _zone_time(zone, x)
        hh = x.hour(hh)
        c.text(label, cx, cy, x.acc, 1, 0.55 if i else 1.0)
        c.text(f"{hh:02d}:{mm:02d}", cx + 15, cy, x.acc, 1, 0.8 if i else 1.0)
    for yy in range(0, 12, 2):
        c.px(36, yy, x.acc, 0.2)
    sec_line(c, x, 14, marks=False)


def dateline(c, x):
    draw_time(c, x, THIN2, 3, at=2, gap=2)
    for yy in range(1, 15):
        c.px(39, yy, x.acc, 0.3)
    today = x.date.tm_wday
    for i, ch in enumerate(DAYS):
        c.text(ch, 42 + i * 4, 1, WHITE if i == today else x.acc, 1, 1.0 if i == today else 0.35)
    d = f"{x.date.tm_mday:02d}.{x.date.tm_mon:02d}.{x.date.tm_year % 100:02d}"
    c.text(d, 42, 7, x.acc, 1, 0.85)
    for i in range(28):
        c.px(42 + i, 14, x.acc, 0.9 if i * 60 / 28 <= x.t else 0.2)


def spectrum(c, x):
    for i in range(24):
        k = x.T * 7
        n0, n1 = noise(int(k) + i * 13.7), noise(int(k) + 1 + i * 13.7)
        v = n0 + (n1 - n0) * (k % 1.0)
        v *= 0.6 + 0.4 * math.sin(i * 0.5 + x.T * 0.7) ** 2
        h = rnd(2 + v * 13)
        for yy in range(h):
            for xx in (3 * i, 3 * i + 1):
                c.px(xx, 15 - yy, x.acc, 0.3 + 0.3 * yy / 14)
    items, width = layout(THIN2, x.text(), 2)
    x0 = (W - width) // 2
    c.shade(x0 - 3, 2, width + 6, 12, 0.93)
    draw_time(c, x, THIN2, 3, gap=2)


def _path(*pts):
    out = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        n = max(abs(x1 - x0), abs(y1 - y0))
        for k in range(n):
            out.append((x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n))
    out.append(pts[-1])
    return [(rnd(a), rnd(b)) for a, b in out]


CIRCUIT = [_path((0, 2), (6, 2), (10, 6), (17, 6)),
           _path((0, 8), (17, 8)),
           _path((0, 14), (6, 14), (10, 10), (17, 10))]


def circuit(c, x):
    for i, p in enumerate(CIRCUIT):
        for side in (0, 1):
            pts = [(px if side == 0 else 71 - px, py) for px, py in p]
            for px, py in pts:
                c.px(px, py, x.acc, 0.3)
            c.px(*pts[-1], x.acc, 0.9)
            c.px(pts[-1][0] + (1 if side == 0 else -1), pts[-1][1], x.acc, 0.9)
            head = (x.T * (9 + 3 * i) + i * 7 + side * 5) % (len(pts) + 8)
            for k in range(5):
                idx = rnd(head) - k
                if 0 <= idx < len(pts):
                    c.px(*pts[idx], WHITE if k == 0 else x.acc, 1.0 if k == 0 else (1 - k / 5) * 0.8)
    draw_time(c, x, THIN2, 3, at=19, gap=2)


DESIGNS = {
    "seg": (seg, "Seven-segment LCD with ghost segments and a 60-tick seconds line.", {}),
    "thin": (thin, "Tall thin segments between two vertical second-meters.", {}),
    "matrix": (matrix, "5x7 LED dot matrix with a bright scan column sweeping each second.", {}),
    "perimeter": (perimeter, "The seconds run around the edge of the display.", {}),
    "radar": (radar, "Analog dial with a sweeping radar hand and a digital readout.", {}),
    "binary": (binary, "BCD binary dots for h:m:s next to the digital time.", {}),
    "brackets": (brackets, "HUD corner brackets, side labels and a second marker.", {}),
    "pulse": (pulse, "ECG trace scrolling behind the time, one beat a second.", {}),
    "telemetry": (telemetry, "Date, time, seconds and a live equaliser.", {}),
    "glitch": (glitch, "Solid digits that tear, ghost and scatter in short bursts.", {}),
    "holo": (holo, "A scan beam lights up the digits as it passes.", {}),
    "hexbg": (hexbg, "Hex dump scrolling above and below, time in a darkened window.", {}),
    "bars3": (bars3, "Hours, minutes and seconds as three segmented progress bars.", {}),
    "arc": (arc, "Seconds fill a disc clockwise; time beside it.", {}),
    "odometer": (odometer, "Digits roll like a counter when the minute changes.", {}),
    "tape": (tape, "HUD heading tape sliding under the time.", {}),
    "rain": (rain, "Falling code columns behind the time.", {}),
    "target": (target, "Rotating reticle that locks on every ten seconds.", {}),
    "alarm": (alarm, "Hazard stripes and a blinking warning sign; colour and shape are options.", {}),
    "monolith": (monolith, "Full-height thick segments; seconds and minutes as edge meters.", {}),
    "warp": (warp, "Italic digits over horizontal speed streaks.", {}),
    "world": (world, "Local time plus three other zones, with a seconds line.", {}),
    "dateline": (dateline, "Time, weekday strip, date and a seconds line.", {}),
    "spectrum": (spectrum, "Audio-spectrum bars dancing behind the time.", {}),
    "circuit": (circuit, "PCB traces with data pulses running into the digits.", {}),
}
