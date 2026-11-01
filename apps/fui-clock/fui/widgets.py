"""Reusable FUI building blocks. Each draws into a Canvas and takes explicit parameters.

`ph` is the loop phase in 0..1; any motion that is an integer number of cycles per loop is seamless.
"""
import math

from .canvas import BLACK, RED, WHITE, W, H, noise, rnd, text_width

TAU = 2 * math.pi


def brackets(c, color, a=0.9, arm=3):
    """HUD corner brackets."""
    for x, y, dx, dy in ((0, 0, 1, 1), (W - 1, 0, -1, 1), (0, H - 1, 1, -1), (W - 1, H - 1, -1, -1)):
        for i in range(arm):
            c.px(x + i * dx, y, color, a)
            if i:
                c.px(x, y + i * dy, color, a)


def reticle(c, cx, cy, color, a=0.7, hot=False):
    """Crosshair with four tick pairs and diagonal corner dots; `hot` turns the centre white."""
    for dx, dy in ((0, -5), (0, -4), (0, 4), (0, 5), (-6, 0), (-5, 0), (5, 0), (6, 0), (-3, -3), (3, -3), (-3, 3), (3, 3)):
        c.px(cx + dx, cy + dy, color, a)
    c.px(cx, cy, WHITE if hot else color, 1 if hot else 0.5)


def dot_grid(c, color, a=0.14, pitch=4):
    for y in range(2, H, pitch):
        for x in range(2, W, pitch):
            c.px(x, y, color, a)


def wave(c, ph, color, x0=0, x1=W, cy=9, amp=3.4, cycles=3, harmonic=0.8, harmonic_cycles=4,
         thickness=1, fade=0.8, breathe=0.3, direction=1):
    """Oscilloscope trace. cycles = wave periods across one loop (sets the scroll speed), harmonic adds a
    faster ripple, fade dims the left end (0 = none), breathe modulates the amplitude once per loop."""
    a_now = amp * (1 - breathe + breathe * math.sin(TAU * ph) * 0.5 + breathe * 0.5)

    def f(x):
        return (cy + a_now * math.sin(x * 0.32 - direction * TAU * cycles * ph)
                + harmonic * math.sin(x * 0.9 + direction * TAU * harmonic_cycles * ph))

    span = max(1, x1 - x0 - 1)
    for x in range(x0, x1):
        y0, y1 = rnd(f(x)), rnd(f(x + 1))
        al = 1 - fade * (1 - (x - x0) / span)
        for y in range(min(y0, y1), max(y0, y1) + 1):
            for t in range(thickness):
                c.px(x, y + t, color, al)


def baseline(c, color, y=9, a=0.3, step=2):
    for x in range(0, W, step):
        c.px(x, y, color, a)


def ruler(c, color, y=15, step=6, a=0.5):
    for x in range(0, W, step):
        c.px(x, y, color, a)
        c.px(x, y - 1, color, a * 0.5)


def gauge(c, value, color, x=2, y=8, seg_w=3, gap=1, seg_h=6, segments=17, warn_from=13, warn_color=RED,
          unlit=0.18, peak=None, ticks=True):
    """Segmented bar. value 0..1; segments from `warn_from` on use warn_color; `peak` (0..1) marks a hold."""
    lit = rnd(value * segments)
    for i in range(segments):
        col = warn_color if i >= warn_from else color
        c.rect(x + i * (seg_w + gap), y, seg_w, seg_h, col, 1.0 if i < lit else unlit)
        if ticks:
            c.px(x + 1 + i * (seg_w + gap), y - 2, color, 0.8 if i % 4 == 0 else 0.35)
    if peak is not None:
        c.px(x + 1 + min(rnd(peak * segments), segments - 1) * (seg_w + gap), y + seg_h, WHITE, 0.9)


def bars(c, step, color, x=44, base=12, n=8, bar_w=2, gap=1, max_h=9, seed=0, ramp=True):
    """Bar-chart equaliser; heights are stable noise per time step."""
    for i in range(n):
        h = rnd(1 + noise(step - i + seed) * (max_h - 1))
        a = (0.4 + 0.6 * i / max(1, n - 1)) if ramp else 1.0
        for yy in range(h):
            for w in range(bar_w):
                c.px(x + i * (bar_w + gap) + w, base - yy, color, a)


def scanline(c, ph, color, x0=-14, x1=86, trail=12, center=8, falloff=9):
    """Sweeping beam with a fading trail; returns the head x so callers can react (lock-on)."""
    sx = x0 + (x1 - x0) * ph
    for k in range(trail):
        a = (1 - k / trail) ** 2
        for y in range(H):
            c.px(sx - k, y, color, a * (0.35 + 0.65 * (1 - abs(y - center) / falloff)))
    return sx


def hexstream(c, ph, color, y, seed, a=0.35, chars=20, direction=1):
    """A row of hex text scrolling one full text period (chars*4 px) per loop."""
    s = "".join("0123456789ABCDEF"[int(noise(seed + i) * 16)] for i in range(chars))
    period = chars * 4
    shift = int(ph * period)
    offset = shift if direction > 0 else (period - shift) % period
    c.text(s + s, -offset, y, color, 1, a)


def readout(c, label, value, x, y, color, a_label=0.6):
    """Small label above/left of a value, e.g. ALT 12345."""
    c.text(label, x, y, color, 1, a_label)
    c.text(value, x + text_width(label) + 4, y, color)


def warn_triangle(c, cx, top, color, a):
    for r in range(10):
        y, half = top + r, rnd(r * 0.5)
        if r == 9:
            for x in range(cx - 5, cx + 6):
                c.px(x, y, color, a)
        else:
            c.px(cx - half, y, color, a)
            c.px(cx + half, y, color, a)
    for y in (top + 4, top + 5, top + 6, top + 8):
        c.px(cx, y, color, a)


def hazard(c, shift, color=RED, a=0.8):
    """Moving diagonal warning stripes on the top and bottom two rows."""
    for x in range(W):
        if (x - shift) % 8 < 4:
            c.px(x, 0, color, a)
            c.px(x, 1, color, a)
        if (x + shift) % 8 < 4:
            c.px(x, 14, color, a)
            c.px(x, 15, color, a)


def banner(c, msg, color, a=1.0, y=6, backdrop=0.85, rows=(5, 6)):
    """Centered one-line message over a darkened band (hides what is behind it)."""
    c.shade(0, rows[0], W, rows[1], backdrop)
    c.text(msg, rnd(W / 2 - text_width(msg) / 2), y, color, 1, a)
