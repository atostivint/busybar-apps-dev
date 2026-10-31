#!/usr/bin/env python3
"""Generates the Halloween sprites as BUSY Bar .anim files + a preview GIF.

    python tools/gen_halloween.py

Writes apps/halloween-clock/assets/{pumpkin,bat}.anim and
tools/preview/sprites.gif (a 10x LED-style preview, for eyeballing only).

Sprites are described as shape functions over continuous coordinates and
rasterised with 4x4 supersampling, so 16x16 art gets smooth edges on the LEDs.
"""
import math
from pathlib import Path

from make_anim import rgba_to_bgra, write_anim

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "apps" / "halloween-clock" / "assets"
PREVIEW = ROOT / "tools" / "preview"
SIZE, FPS, SS = 16, 20, 4


def rasterise(shape, t):
    """shape(x, y, t) -> (r, g, b) or None. Returns RGBA bytes, SIZE x SIZE."""
    out = bytearray()
    for py in range(SIZE):
        for px in range(SIZE):
            n, sr, sg, sb = 0, 0, 0, 0
            for sy in range(SS):
                for sx in range(SS):
                    c = shape(px + (sx + 0.5) / SS, py + (sy + 0.5) / SS, t)
                    if c:
                        n += 1
                        sr, sg, sb = sr + c[0], sg + c[1], sb + c[2]
            if n:
                out.extend((round(sr / n), round(sg / n), round(sb / n), round(255 * n / (SS * SS))))
            else:
                out.extend((0, 0, 0, 0))
    return bytes(out)


def lerp(a, b, k):
    return tuple(round(a[i] + (b[i] - a[i]) * k) for i in range(3))


def scale(c, k):
    return tuple(max(0, min(255, round(v * k))) for v in c)


# --------------------------------------------------------------------------- pumpkin

# Face cells (column, row) lit by the candle inside.
EYES = {(5, 7), (4, 8), (5, 8), (6, 8), (10, 7), (9, 8), (10, 8), (11, 8)}
MOUTH = {(x, 11) for x in range(4, 12)} | {(5, 12), (6, 12), (9, 12), (10, 12)}
FACE = EYES | MOUTH
FRAMES_PUMPKIN = 40  # 2 s loop


def flicker(f):
    """0.55..1.0, built from whole-number harmonics so the loop is seamless."""
    p = 2 * math.pi * f / FRAMES_PUMPKIN
    return 0.78 + 0.14 * math.sin(p) + 0.08 * math.sin(3 * p + 1.3)


def pumpkin(x, y, f):
    glow = flicker(f)
    # stem
    if 7.0 <= x <= 9.2 and 2.0 <= y <= 4.4 and not (x > 8.6 and y < 2.6):
        return (70, 150, 40)
    # body
    cx, cy, rx, ry = 8.0, 9.3, 7.4, 5.3
    d = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2
    if d > 1.0:
        return None
    if (int(x), int(y)) in FACE:
        return lerp((235, 90, 0), (255, 240, 90), (glow - 0.55) / 0.45)
    body = (205, 70, 0)
    shade = 0.55 + 0.45 * (1 - d ** 1.5)           # darker toward the edge
    ribs = 0.88 if int(x) in (4, 11) else 1.0      # two faint ribs
    return scale(body, shade * ribs * (0.9 + 0.1 * glow))


# --------------------------------------------------------------------------- bat

FRAMES_BAT = 12  # 0.6 s per wing beat


def inside(poly, x, y):
    """Even-odd point in polygon."""
    hit = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def bat(x, y, f):
    up = math.cos(2 * math.pi * f / FRAMES_BAT)       # +1 wings up, -1 wings down
    by = 8.6 + 0.8 * up                               # body dips as the wings rise
    tip_y = 7.8 - 4.6 * up
    reach = 1.0 + 1.3 * abs(up)                       # wings fold in at the extremes
    body_c, wing_c, eye_c = (130, 60, 220), (175, 85, 255), (255, 60, 60)

    for side in (-1, 1):
        shoulder = (8 + side * 1.2, by - 1.0)
        tip = (8 + side * (8 - reach), tip_y)
        root = (8 + side * 1.6, by + 2.4)

        def along(k, pull):
            """Point k of the way from tip to root, pulled `pull` px toward the body (scallop)."""
            px = tip[0] + (root[0] - tip[0]) * k
            py = tip[1] + (root[1] - tip[1]) * k
            return (px + (shoulder[0] - px) * 0.0 - side * pull, py)

        poly = [shoulder, tip, along(0.33, -0.0), along(0.36, 1.4), along(0.68, 0.0), along(0.7, 1.2), root]
        if inside(poly, x, y):
            return wing_c
    # ears, head, body
    for ex in (-1, 1):
        if inside([(8 + ex * 0.4, by - 2.6), (8 + ex * 1.7, by - 4.0), (8 + ex * 1.9, by - 2.3)], x, y):
            return body_c
    if ((x - 8) / 1.9) ** 2 + ((y - (by - 1.7)) / 1.7) ** 2 <= 1:
        if abs(abs(x - 8) - 0.8) < 0.45 and abs(y - (by - 1.9)) < 0.45:
            return eye_c
        return body_c
    if ((x - 8) / 1.7) ** 2 + ((y - (by + 0.5)) / 2.5) ** 2 <= 1:
        return body_c
    return None


# --------------------------------------------------------------------------- output

def build(name, shape, frames):
    rgba = [rasterise(shape, f) for f in range(frames)]
    write_anim(ASSETS / f"{name}.anim", [rgba_to_bgra(r) for r in rgba], SIZE, SIZE, FPS)
    print(f"wrote {ASSETS / (name + '.anim')} ({frames} frames)")
    return rgba


def preview(pumpkin_rgba, bat_rgba, cell=10):
    """Side-by-side LED-style GIF on a 72x16 black canvas (time digits not drawn)."""
    from PIL import Image, ImageDraw

    n = math.lcm(len(pumpkin_rgba), len(bat_rgba))
    imgs = []
    for i in range(n):
        img = Image.new("RGB", (72 * cell, 16 * cell), (14, 14, 16))
        d = ImageDraw.Draw(img)
        for y in range(16):
            for x in range(72):
                d.ellipse([x * cell + 1, y * cell + 1, x * cell + cell - 2, y * cell + cell - 2], fill=(30, 30, 34))
        for rgba, ox in ((pumpkin_rgba[i % len(pumpkin_rgba)], 0), (bat_rgba[i % len(bat_rgba)], 56)):
            for y in range(16):
                for x in range(16):
                    r, g, b, a = rgba[(y * 16 + x) * 4:(y * 16 + x) * 4 + 4]
                    if a:
                        k = a / 255
                        d.ellipse([(ox + x) * cell + 1, y * cell + 1, (ox + x) * cell + cell - 2, y * cell + cell - 2],
                                  fill=(round(r * k), round(g * k), round(b * k)))
        imgs.append(img)
    PREVIEW.mkdir(parents=True, exist_ok=True)
    out = PREVIEW / "sprites.gif"
    imgs[0].save(out, save_all=True, append_images=imgs[1:], duration=1000 // FPS, loop=0)
    print(f"wrote {out}")


if __name__ == "__main__":
    ASSETS.mkdir(parents=True, exist_ok=True)
    p = build("pumpkin", pumpkin, FRAMES_PUMPKIN)
    b = build("bat", bat, FRAMES_BAT)
    preview(p, b)
