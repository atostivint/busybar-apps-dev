"""A minute of clock -> frames -> .anim.

The bar plays a file; it cannot draw a clock. So each minute is rendered ahead as one 60 s animation (digits,
seconds hand and ambient motion included), uploaded, and started exactly on the minute.
"""
import time

from anim import rgba_to_bgra, write_anim

from .canvas import W, H, Canvas, text_width, WHITE
from .canvas import RED
from .designs import DESIGNS, Ctx

FRAME_S = 60


def parse_zones(spec):
    """'NYC=America/New_York,TYO=Asia/Tokyo' -> [('NYC', 'America/New_York'), ...]"""
    out = []
    for part in spec.split(","):
        part = part.strip()
        if "=" in part:
            label, zone = part.split("=", 1)
            out.append((label.strip().upper()[:3], zone.strip()))
        elif part:
            out.append((part.upper()[:3], part))
    return out


def pick(design, minute_epoch, rotate, order):
    """The design for the minute starting at minute_epoch; 'all' cycles through `order` every `rotate` minutes."""
    if design != "all":
        return design
    return order[(minute_epoch // 60 // max(1, rotate)) % len(order)]


def make_ctx(E, t, acc, hour12, blink, zones, alarm):
    lt = time.localtime(E)
    pt = time.localtime(E - 60)
    return Ctx(E + t, t, lt.tm_hour, lt.tm_min, (pt.tm_hour, pt.tm_min), lt, acc, hour12, blink, zones, alarm)


def toast(c, label, acc):
    """Name of the design, in a darkened band: shown briefly after the wheel switches design."""
    c.shade(0, 5, W, 7, 0.92)
    c.text(label, (W - text_width(label)) // 2, 6, WHITE, 1, 1.0)
    for x in range(W):
        c.px(x, 4, acc, 0.5)
        c.px(x, 12, acc, 0.5)


def render_minute(design, E, fps, acc, hour12, blink, zones, min_alpha, alarm=(RED, "triangle"), first=0, last=None,
                  prev=True, toast_until=0.0):
    """RGBA frames for the minute starting at epoch E (frame i is shown at E + i/fps), from frame `first` up to `last`.
    Until `toast_until` (seconds into the minute) the design's name is overlaid."""
    draw = DESIGNS[design][0]
    canvas = Canvas(min_alpha)
    out = []
    for i in range(first, last or FRAME_S * fps):
        canvas.clear()
        x = make_ctx(E, i / fps, acc, hour12, blink, zones, alarm)
        if not prev:
            x.prev = None
        draw(canvas, x)
        if i / fps < toast_until:
            toast(canvas, design.upper(), acc)
        out.append(canvas.rgba())
    return out


def render_at(design, now, fps, acc, hour12, blink, zones, min_alpha, alarm=(RED, "triangle")):
    """The one frame the minute animation shows at epoch `now` (same frame grid as render_minute, so a live
    frame and the pre-rendered animation agree pixel for pixel)."""
    E = int(now // 60) * 60
    i = min(int((now - E) * fps), FRAME_S * fps - 1)
    canvas = Canvas(min_alpha)
    x = make_ctx(E, i / fps, acc, hour12, blink, zones, alarm)
    x.prev = None
    DESIGNS[design][0](canvas, x)
    return canvas.rgba()


def write(path, frames, fps):
    write_anim(path, [rgba_to_bgra(f) for f in frames], W, H, fps)
