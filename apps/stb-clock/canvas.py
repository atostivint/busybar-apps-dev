"""A 72x16 RGB pixel canvas and a 3x5 font: everything the clock card needs.

The belt itself is drawn by the firmware from XPM bitmaps; this canvas is used to draw the clock card
(background, border, digits, seconds tick) as one small xpmbitmap, and by the preview tool.
"""
W, H = 72, 16

_FONT = {
    "0": "111,101,101,101,111", "1": "010,110,010,010,111", "2": "111,001,111,100,111",
    "3": "111,001,111,001,111", "4": "101,101,111,001,001", "5": "111,100,111,001,111",
    "6": "111,100,111,101,111", "7": "111,001,001,010,010", "8": "111,101,111,101,111",
    "9": "111,101,111,001,111", ":": "0,1,0,1,0", " ": "00,00,00,00,00",
    "A": "111,101,111,101,101", "P": "111,101,111,100,100", "M": "101,111,111,101,101",
}
GLYPHS = {k: v.split(",") for k, v in _FONT.items()}


def text_width(s, scale=1, gap=None):
    gap = scale if gap is None else gap
    return sum(len(GLYPHS.get(ch, GLYPHS[" "])[0]) * scale + gap for ch in s) - gap


class Canvas:
    """RGB bytes, no alpha: the LED is opaque and black is off."""

    def __init__(self, w=W, h=H):
        self.w, self.h = w, h
        self.buf = bytearray(w * h * 3)

    def px(self, x, y, color):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.buf[i:i + 3] = bytes(color)

    def rect(self, x, y, w, h, color):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.px(xx, yy, color)

    def text(self, s, x, y, color, scale=1, gap=None):
        gap = scale if gap is None else gap
        cx = x
        for ch in s:
            g = GLYPHS.get(ch, GLYPHS[" "])
            for r, row in enumerate(g):
                for q, bit in enumerate(row):
                    if bit == "1":
                        self.rect(cx + q * scale, y + r * scale, scale, scale, color)
            cx += len(g[0]) * scale + gap

    def blit(self, grid, x, y):
        """`grid` is a belt.Badge-compatible PIL image."""
        for yy in range(grid.height):
            for xx in range(grid.width):
                self.px(x + xx, y + yy, grid.getpixel((xx, yy)))
