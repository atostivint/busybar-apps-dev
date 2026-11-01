"""Digit fonts for the clock designs.

A font's glyph(ch) returns (width, pixels); pixels is a tuple of (x, y, on). `on` False is a "ghost" mark: an
unlit segment or dot that a design may draw faintly (or skip). Keeping glyphs as pixel lists lets designs move,
clip and displace digits freely.
"""
from functools import lru_cache

from .canvas import GLYPHS


class Bitmap:
    """The 3x5 canvas font, scaled up with no gaps."""

    def __init__(self, scale=2):
        self.scale = scale
        self.h = 5 * scale

    @lru_cache(maxsize=None)
    def glyph(self, ch):
        g = GLYPHS.get(ch, GLYPHS[" "])
        s, out = self.scale, []
        for r, row in enumerate(g):
            for q, bit in enumerate(row):
                if bit == "1":
                    out += [(q * s + i, r * s + j, True) for i in range(s) for j in range(s)]
        return len(g[0]) * s, tuple(out)


_DOTS = {
    "0": "01110,10001,10011,10101,11001,10001,01110", "1": "00100,01100,00100,00100,00100,00100,01110",
    "2": "01110,10001,00001,00010,00100,01000,11111", "3": "11111,00010,00100,00010,00001,10001,01110",
    "4": "00010,00110,01010,10010,11111,00010,00010", "5": "11111,10000,11110,00001,00001,10001,01110",
    "6": "00110,01000,10000,11110,10001,10001,01110", "7": "11111,00001,00010,00100,01000,01000,01000",
    "8": "01110,10001,10001,01110,10001,10001,01110", "9": "01110,10001,10001,01111,00001,00010,01100",
    ":": "0,0,1,0,1,0,0", " ": "0,0,0,0,0,0,0",
}


class Dots:
    """5x7 dot matrix; `pitch` px between dots (2 = a lit dot, a dark gap, like a real LED board)."""

    def __init__(self, pitch=2):
        self.pitch = pitch
        self.h = 6 * pitch + 1

    @lru_cache(maxsize=None)
    def glyph(self, ch):
        rows = _DOTS.get(ch, _DOTS[" "]).split(",")
        p = self.pitch
        out = [(q * p, r * p, bit == "1") for r, row in enumerate(rows) for q, bit in enumerate(row)]
        return (len(rows[0]) - 1) * p + 1, tuple(out)


_SEGS = {"0": "abcdef", "1": "bc", "2": "abdeg", "3": "abcdg", "4": "bcfg", "5": "acdfg", "6": "acdefg",
         "7": "abc", "8": "abcdefg", "9": "abcdfg", " ": ""}


class Seg:
    """Seven segments. w x h is the digit box, t the stroke, slant the lean (px the top shifts right)."""

    def __init__(self, w=8, h=11, t=2, slant=0):
        self.w, self.h, self.t, self.slant = w, h, t, slant

    @lru_cache(maxsize=None)
    def glyph(self, ch):
        w, h, t, slant = self.w, self.h, self.t, self.slant
        mid = (h - t) // 2
        up, lo = mid + t - 2, h - 1 - mid - t
        rects = {"a": (1, 0, w - 2, t), "d": (1, h - t, w - 2, t), "g": (1, mid, w - 2, t),
                 "f": (0, 1, t, up), "b": (w - t, 1, t, up), "e": (0, mid + t, t, lo), "c": (w - t, mid + t, t, lo)}
        if ch == ":":
            d = max(1, t)
            ys = (round(h * 0.30) - d // 2, round(h * 0.70) - d // 2)
            return d + slant, tuple((x + self._lean(y), y + j, True) for y in ys for j in range(d) for x in range(d))
        lit = _SEGS.get(ch, "")
        pix = {}
        for name, (rx, ry, rw, rh) in rects.items():
            for y in range(ry, ry + rh):
                for x in range(rx, rx + rw):
                    key = (x + self._lean(y), y)
                    pix[key] = pix.get(key, False) or name in lit
        return w + slant, tuple((x, y, on) for (x, y), on in pix.items())

    def _lean(self, y):
        return round(self.slant * (self.h - 1 - y) / max(1, self.h - 1))


def layout(font, s, gap=1):
    """[(char, x, pixels)] for a string and its total width."""
    out, x = [], 0
    for ch in s:
        w, px = font.glyph(ch)
        out.append((ch, x, px))
        x += w + gap
    return out, max(0, x - gap)


def put(c, pixels, ox, oy, color, a_on=1.0, a_off=0.0):
    for x, y, on in pixels:
        a = a_on if on else a_off
        if a > 0:
            c.px(ox + x, oy + y, color, a)
