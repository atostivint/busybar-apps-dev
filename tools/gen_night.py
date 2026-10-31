#!/usr/bin/env python3
"""Night-mode variant of the graveyard scene, for the lowest bar brightness.

    python tools/gen_night.py

Writes apps/halloween-clock/assets/night_*.anim (the app uses them with --night). The day
assets are not touched.

At the lowest brightness the firmware cannot render dim or mixed colours: they show up as pale
white-blue dots, a faint orange glow as green dots. So the night art is hand-drawn pixel art:
every sprite below is an ASCII grid, one character per LED, in a handful of saturated palette
colours. Fully opaque or empty, no alpha, no halo, no glow behind the time, nothing dimmer than
MIN_LIT. Animation only moves whole sprites by whole pixels or swaps colours.
"""
import math

from gen_graveyard import BOLT, H, SCENE_FRAMES, SCENERY_FRAMES, STARS, THUNDER, THUNDER_FRAMES, W
from gen_halloween import ASSETS, FPS
from make_anim import rgba_to_bgra, write_anim

BAT_FRAMES = 60
MIN_LIT = 80

PALETTE = {
    "B": (110, 60, 0),      # tree brown
    "O": (205, 72, 0),      # pumpkin
    "o": (255, 122, 0),     # bright orange (pumpkin flicker)
    "Y": (255, 215, 60),    # pumpkin face
    "s": (60, 140, 35),     # stem
    "G": (0, 150, 0),       # grass
    "E": (0, 84, 0),        # earth
    "g": (112, 112, 120),   # stone grey
    "M": (236, 228, 168),   # moon
    "c": (190, 178, 105),   # moon crater
    "R": (200, 0, 0),       # blood moon
    "r": (140, 0, 0),       # blood moon crater
    "w": (240, 248, 255),   # white (bolt)
    "C": (96, 104, 140),    # cloud
    "L": (150, 160, 200),   # cloud top edge
    "*": (170, 190, 255),   # star
    "V": (170, 0, 255),     # bat
}
assert all(max(c) >= MIN_LIT for c in PALETTE.values())


class Canvas:
    def __init__(self):
        self.px = [None] * (W * H)

    def put(self, x, y, key):
        if 0 <= x < W and 0 <= y < H and key not in (None, ".", " "):
            self.px[y * W + x] = PALETTE[key]

    def blit(self, art, x0, y0):
        for dy, row in enumerate(art):
            for dx, ch in enumerate(row):
                self.put(x0 + dx, y0 + dy, ch)

    def rgba(self):
        out = bytearray()
        for c in self.px:
            out.extend((*c, 255) if c else (0, 0, 0, 0))
        return bytes(out)


# ---- hand-drawn sprites (one character per LED) ----------------------------------------------

TREE = [          # 12 wide, 14 tall; the branches (top rows) sway in the wind
    "B..........B",
    ".B........B.",
    ".B..B..B..B.",
    "..B.B..B.B..",
    "..BBB..BBB..",
    "...BBBBBB...",
    "....BBBB....",
    ".....BB.....",
    ".....BB.....",
    ".....BB.....",
    "....BBB.....",
    "....BBB.....",
    "...BBBBB....",
    "..BBB.BBB...",
]
TREE_XY = (2, 0)
TREE_PAD = 2      # room for the sway on both sides
TREE_REACH = 8    # rows from the top that move with the wind


def tree_art(f):
    """The tree bent by the wind: the further up, the more a row is pushed (whole pixels only)."""
    gust = round(1.7 * math.sin(2 * math.pi * f / SCENERY_FRAMES))
    rows = []
    for i, row in enumerate(TREE):
        shift = round(gust * max(0, TREE_REACH - i) / TREE_REACH)
        padded = "." * (TREE_PAD * 2) + row + "." * (TREE_PAD * 2)
        rows.append(padded[TREE_PAD * 2 - shift - TREE_PAD:TREE_PAD * 2 - shift - TREE_PAD + len(row) + 2 * TREE_PAD])
    return rows


PUMPKIN = [       # 9x9: triangle eyes, nose, toothy grin; must stay left of the digits (x < 19)
    "....s....",
    "..OOOOO..",
    ".OOOOOOO.",
    "OOYOOOYOO",
    "OYYYOYYYO",
    "OOOOOOOOO",
    "OYOYOYOYO",
    ".OYYYYYO.",
    "..OOOOO..",
]
PUMPKIN_XY = (10, 5)
PUMPKIN_EYES = {(x, y) for y, row in enumerate(PUMPKIN[:5]) for x, ch in enumerate(row) if ch == "Y"}   # these flicker

STONES = [
    ([".gg.", "gggg", "gggg", "gggg"], (55, 10)),
    ([".g.", "ggg", "ggg"], (61, 11)),
    ([".g.", "ggg", ".g.", ".g.", ".g."], (67, 9)),    # cross
]

MOON_X, MOON_Y = 60, 1
MOON = {
    "full": [
        "..MMMM..",
        ".MMcMMM.",
        "MMMMMMMM",
        "MMMMMcMM",
        "MMcMMMMM",
        "MMMMMMMM",
        ".MMMcMM.",
        "..MMMM..",
    ],
    "half": [          # right half lit, the dark side is only outlined
        "..ggMM..",
        ".g..MMM.",
        "g...MMMM",
        "g...MMMM",
        "g...MMMM",
        "g...MMMM",
        ".g..MMM.",
        "..ggMM..",
    ],
    "crescent": [
        "..MMgg..",
        ".MM...g.",
        "MM.....g",
        "MM.....g",
        "MM.....g",
        "MMM....g",
        ".MMM.gg.",
        "..MMgg..",
    ],
    "blood": [
        "..RRRR..",
        ".RRRRRR.",
        "RRRrRRRR",
        "RRRRRRRR",
        "RRrRRRRR",
        "RRRRRrRR",
        ".RRRRRR.",
        "..RRRR..",
    ],
}

CLOUD_S = ["..LL.....", ".LCCLLL..", "CCCCCCCC."]     # small, 9x3
CLOUD_XS = [".LL..", "LCCLL", "CCCCC"]               # tiny, 5x3
CLOUD_L = ["...LLL.....", ".LLCCCLL...", "LCCCCCCCCL.", "CCCCCCCCCCC"]   # large, 11x4

BAT_UP = ["V.....V", "VV.V.VV", ".VVVVV."]
BAT_DOWN = ["..VVV..", ".VVVVV.", "VV...VV", "V.....V"]


# ---- layers ---------------------------------------------------------------------------------

def drift(base_x, amp, phase, f):
    """Whole-pixel sway, one exact cycle per SCENE_FRAMES so the loop is seamless."""
    return base_x + round(amp * math.sin(2 * math.pi * f / SCENE_FRAMES + phase))


SKY = {  # weather -> [(sprite, base x, y, drift amplitude, phase)]
    "calm": [(CLOUD_XS, 24, 0, 4, 0.0)],
    "stormy": [(CLOUD_L, 54, 2, 5, 0.0), (CLOUD_S, 40, 0, 4, 1.7), (CLOUD_S, 22, 0, 3, 3.1)],
    "foggy": [(CLOUD_L, 54, 3, 5, 0.4), (CLOUD_S, 40, 0, 4, 2.2), (CLOUD_XS, 22, 1, 3, 4.0)],
}


def sky_frame(weather, f):
    cv = Canvas()
    if weather == "calm":
        for sx, sy, _ in STARS:
            cv.put(sx, sy, "*")
    for art, bx, y, amp, ph in SKY[weather]:
        cv.blit(art, drift(bx, amp, ph, f), y)
    return cv.rgba()


def moon_frame(kind):
    cv = Canvas()
    cv.blit(MOON[kind], MOON_X, MOON_Y)
    return cv.rgba()


def grass_top(x):
    return round(14.0 + 0.55 * math.sin(x / 5.5 + 0.8) + 0.45 * math.sin(x / 2.3 + 2.0))


def scenery_frame(f):
    cv = Canvas()
    for x in range(W):             # green floor: a grass line on top, earth under it
        top = grass_top(x)
        cv.put(x, top, "G")
        for y in range(top + 1, H):
            cv.put(x, y, "E")
    cv.blit(tree_art(f), TREE_XY[0] - TREE_PAD, TREE_XY[1])
    px, py = PUMPKIN_XY
    cv.blit(PUMPKIN, px, py)
    if f % 40 >= 30:               # the candle gutters: the eyes go orange for a moment
        for dx, dy in PUMPKIN_EYES:
            cv.put(px + dx, py + dy, "o")
    for art, (x, y) in STONES:
        cv.blit(art, x, y)
    # redraw the grass over the tree roots and the stones' feet
    for x in range(W):
        cv.put(x, grass_top(x), "G")
    return cv.rgba()


def line(cv, a, b, key):
    """Bresenham line between two LEDs."""
    (x0, y0), (x1, y1) = a, b
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    while True:
        cv.put(x0, y0, key)
        if (x0, y0) == (x1, y1):
            return
        e2 = 2 * err
        if e2 >= dy:
            err, x0 = err + dy, x0 + sx
        if e2 <= dx:
            err, y0 = err + dx, y0 + sy


def thunder_frame(f):
    cv = Canvas()
    if THUNDER[f][1]:
        pts = [(round(x), min(H - 1, round(y))) for x, y in BOLT]
        for a, b in zip(pts, pts[1:]):
            line(cv, a, b, "w")
    return cv.rgba()


def bat_frame(direction, low, f):
    cv = Canvas()
    u = f / (BAT_FRAMES - 1)
    cx = (-7 + 86 * u) if direction > 0 else (79 - 86 * u)
    cy = (10.2 - 2.6 * math.sin(math.pi * u)) if low else (6.5 - 4.2 * math.sin(math.pi * u))
    art = BAT_UP if (f // 5) % 2 == 0 else BAT_DOWN
    cv.blit(art, round(cx) - len(art[0]) // 2, round(cy) - len(art) // 2)
    return cv.rgba()


# ---- output ---------------------------------------------------------------------------------

def write(name, frames):
    allowed = set(PALETTE.values())
    for fr in frames:   # sanity: opaque or empty, palette colours only
        for i in range(0, len(fr), 4):
            assert fr[i + 3] in (0, 255) and (fr[i + 3] == 0 or tuple(fr[i:i + 3]) in allowed)
    write_anim(ASSETS / f"night_{name}.anim", [rgba_to_bgra(r) for r in frames], W, H, FPS)
    print(f"wrote night_{name}.anim ({len(frames)} frames)")
    return frames


if __name__ == "__main__":
    ASSETS.mkdir(parents=True, exist_ok=True)
    for old in ASSETS.glob("night_*.anim"):
        old.unlink()
    for kind in MOON:
        write(f"moon_{kind}", [moon_frame(kind)] * 20)
    for weather in SKY:
        write(f"sky_{weather}", [sky_frame(weather, f) for f in range(SCENE_FRAMES)])
    write("scenery", [scenery_frame(f) for f in range(SCENERY_FRAMES)])
    for name, direction, low in (("bat_lr_high", 1, False), ("bat_rl_high", -1, False),
                                 ("bat_lr_low", 1, True), ("bat_rl_low", -1, True)):
        write(name, [bat_frame(direction, low, f) for f in range(BAT_FRAMES)])
    write("thunder", [thunder_frame(f) for f in range(THUNDER_FRAMES)])
