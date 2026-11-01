"""A 72x16 RGB canvas with alpha blending, a 3x5 pixel font and a global brightness floor.

Everything draws over black (LED off). `min_alpha` lifts any faint-but-visible mark to a level the LEDs
actually show: below ~0.25 a lit pixel vanishes on the real matrix.
"""
import math

W, H = 72, 16

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 60, 40)
GREEN = (60, 255, 120)
AMBER = (255, 176, 0)

_FONT = {
    "0": "111,101,101,101,111", "1": "010,110,010,010,111", "2": "111,001,111,100,111", "3": "111,001,111,001,111",
    "4": "101,101,111,001,001", "5": "111,100,111,001,111", "6": "111,100,111,101,111", "7": "111,001,001,010,010",
    "8": "111,101,111,101,111", "9": "111,101,111,001,111",
    "A": "111,101,111,101,101", "B": "110,101,110,101,110", "C": "111,100,100,100,111", "D": "110,101,101,101,110",
    "E": "111,100,110,100,111", "F": "111,100,110,100,100", "G": "111,100,101,101,111", "H": "101,101,111,101,101",
    "I": "111,010,010,010,111", "J": "001,001,001,101,111", "K": "101,101,110,101,101", "L": "100,100,100,100,111",
    "M": "101,111,111,101,101", "N": "110,101,101,101,101", "O": "010,101,101,101,010", "P": "111,101,111,100,100",
    "Q": "111,101,101,111,001", "R": "110,101,110,101,101", "S": "111,100,111,001,111", "T": "111,010,010,010,010",
    "U": "101,101,101,101,111", "V": "101,101,101,101,010", "W": "101,101,111,111,101", "X": "101,101,010,101,101",
    "Y": "101,101,010,010,010", "Z": "111,001,010,100,111",
    ":": "0,1,0,1,0", ".": "0,0,0,0,1", "-": "000,000,111,000,000", "%": "101,001,010,100,101",
    "/": "001,001,010,100,100", "+": "000,010,111,010,000", "!": "1,1,1,0,1", " ": "00,00,00,00,00",
}
GLYPHS = {k: v.split(",") for k, v in _FONT.items()}


def rnd(v):
    """JS-style rounding (half up), so pixel positions match the earlier prototypes."""
    return math.floor(v + 0.5)


def noise(n):
    """Deterministic 0..1 hash of a number: stable pseudo-random values per time step."""
    s = math.sin(n * 12.9898) * 43758.5453
    return s - math.floor(s)


def text_width(s, scale=1):
    return sum((len(GLYPHS.get(ch, GLYPHS[" "])[0]) + 1) * scale for ch in s) - scale


class Canvas:
    def __init__(self, min_alpha=0.0):
        self.min_alpha = min_alpha
        self.buf = [0.0] * (W * H * 3)

    def clear(self):
        for i in range(len(self.buf)):
            self.buf[i] = 0.0

    def px(self, x, y, color, a=1.0):
        x, y = rnd(x), rnd(y)
        if x < 0 or y < 0 or x >= W or y >= H or a <= 0.01:
            return
        a = min(1.0, max(a, self.min_alpha))
        i = (y * W + x) * 3
        for k in range(3):
            self.buf[i + k] = self.buf[i + k] * (1 - a) + color[k] * a

    def rect(self, x, y, w, h, color, a=1.0):
        for yy in range(h):
            for xx in range(w):
                self.px(x + xx, y + yy, color, a)

    def shade(self, x, y, w, h, a):
        """Darken a region (a text backdrop). Ignores min_alpha: it is not a visible mark."""
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                if 0 <= xx < W and 0 <= yy < H:
                    i = (yy * W + xx) * 3
                    for k in range(3):
                        self.buf[i + k] *= 1 - a

    def text(self, s, x, y, color, scale=1, a=1.0):
        cx = x
        for ch in s:
            g = GLYPHS.get(ch, GLYPHS[" "])
            for r in range(5):
                for q, bit in enumerate(g[r]):
                    if bit == "1":
                        self.rect(cx + q * scale, y + r * scale, scale, scale, color, a)
            cx += (len(g[0]) + 1) * scale

    def rgba(self):
        """Frame as RGBA bytes; black becomes transparent (LED off)."""
        out = bytearray()
        for i in range(W * H):
            r, g, b = (min(255, rnd(self.buf[i * 3 + k])) for k in range(3))
            out.extend((r, g, b, 255) if r + g + b else (0, 0, 0, 0))
        return bytes(out)
