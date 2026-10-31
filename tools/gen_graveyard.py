#!/usr/bin/env python3
"""Graveyard night scene: one full-bar 72x16 .anim, played behind the time text.

    python tools/gen_graveyard.py

Writes apps/halloween-clock/assets/graveyard.anim and tools/preview/graveyard.gif.
The middle of the bar (x 18..54, rows 3..12) is kept free of scenery so the time
stays readable; only stars and the passing bat use that area, and the time text
is drawn on top of the animation.
"""
import math

from gen_halloween import ASSETS, FPS, PREVIEW, bat, flicker, inside, lerp, rasterise, scale
from make_anim import rgba_to_bgra, write_anim

W, H = 72, 16
FRAMES = 120  # 6 s loop: bat crosses during the first 3 s, then the bar is quiet


def seg_dist(x, y, a, b):
    ax, ay, bx, by = *a, *b
    dx, dy = bx - ax, by - ay
    k = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - (ax + k * dx), y - (ay + k * dy))


# ---- layers (each returns a colour or None) -------------------------------------------

def ground(x, y, f):
    if y >= 15.1:
        return (30, 62, 26)
    # grass tufts on row 14
    if int(y) == 14 and int(x) in (2, 9, 20, 27, 33, 41, 49, 52, 60, 66):
        return (38, 85, 32)
    return None


def tombstones(x, y, f):
    grey = (88, 94, 112)
    # rounded stone
    if 55 <= x <= 58.6 and 12.4 <= y <= 15.2:
        return grey
    if ((x - 56.8) / 1.8) ** 2 + ((y - 12.4) / 1.6) ** 2 <= 1 and y < 12.4:
        return grey
    # small slanted stone
    if 61.3 <= x <= 64.1 and 12.8 <= y <= 15.2 and not (y < 13.4 and x > 63.0):
        return scale(grey, 0.85)
    # cross
    if (68.1 <= x <= 69.3 and 10.4 <= y <= 15.2) or (66.8 <= x <= 70.6 and 11.7 <= y <= 12.9):
        return scale(grey, 0.9)
    return None


def moon(x, y, f):
    d_out = math.hypot(x - 63.6, y - 4.6)
    d_cut = math.hypot(x - 66.2, y - 3.4)
    if d_out <= 4.1 and d_cut > 3.5:
        return (225, 215, 150)
    return None


def tree(x, y, f):
    brown = (96, 56, 26)
    sw = math.sin(2 * math.pi * f / 60)
    if inside([(4.0, 15.4), (5.0, 9.0), (6.2, 9.0), (7.2, 15.4)], x, y):
        return brown
    base = (5.6, 9.2)
    tip_up = (5.0 + 0.8 * sw, 1.8)
    tip_r = (10.6 + 0.8 * sw, 4.2)
    tip_l = (1.6 + 0.7 * sw, 4.6)
    pt = lambda a, b, k: (a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k)
    twigs = [
        (base, tip_up, 1.0), (base, tip_r, 1.0), (base, tip_l, 1.0),
        (pt(base, tip_r, 0.55), (12.2 + 1.0 * sw, 6.8), 0.8),
        (pt(base, tip_up, 0.55), (2.8 + 1.0 * sw, 2.4), 0.8),
        (pt(base, tip_l, 0.55), (0.4 + 0.8 * sw, 7.0), 0.8),
    ]
    for a, b, w in twigs:
        if seg_dist(x, y, a, b) <= w / 2:
            return brown
    return None


def mini_pumpkin(x, y, f):
    g = flicker(f)
    if 14.4 <= x <= 15.6 and 9.6 <= y <= 10.9:
        return (60, 130, 35)
    if ((x - 14.6) / 2.9) ** 2 + ((y - 12.7) / 2.4) ** 2 <= 1:
        if (int(x), int(y)) in {(13, 12), (15, 12), (14, 13)}:
            return lerp((235, 90, 0), (255, 240, 90), (g - 0.55) / 0.45)
        return scale((205, 72, 0), 0.9 + 0.1 * g)
    return None


STARS = [(1, 0, 0), (9, 0, 20), (13, 2, 40), (18, 1, 60), (24, 0, 10), (31, 1, 50), (40, 0, 30),
         (47, 1, 70), (53, 2, 90), (57, 0, 15), (70, 1, 45), (69, 8, 80), (11, 9, 100), (58, 9, 5)]


def stars(x, y, f):
    cx, cy = int(x), int(y)
    for sx, sy, ph in STARS:
        if (sx, sy) == (cx, cy):
            b = 0.35 + 0.35 * math.sin(2 * math.pi * (f + ph) / 40)
            return scale((165, 185, 255), b)
    return None


def passing_bat(x, y, f):
    if f >= 60:
        return None
    u = f / 59
    cx = -7 + 86 * u
    cy = 6.5 - 4.2 * math.sin(math.pi * u)
    s = 0.7
    return bat(8 + (x - cx) / s, 8.6 + (y - cy) / s, f)


LAYERS = [passing_bat, tree, mini_pumpkin, tombstones, moon, ground, stars]  # first hit wins


def scene(x, y, f):
    for layer in LAYERS:
        c = layer(x, y, f)
        if c:
            return c
    return None


def preview(frames, cell=10):
    from PIL import Image, ImageDraw
    imgs = []
    for rgba in frames:
        img = Image.new("RGB", (W * cell, H * cell), (14, 14, 16))
        d = ImageDraw.Draw(img)
        for y in range(H):
            for x in range(W):
                r, g, b, a = rgba[(y * W + x) * 4:(y * W + x) * 4 + 4]
                fill = (30, 30, 34) if not a else (round(r * a / 255), round(g * a / 255), round(b * a / 255))
                d.ellipse([x * cell + 1, y * cell + 1, x * cell + cell - 2, y * cell + cell - 2], fill=fill)
        imgs.append(img)
    PREVIEW.mkdir(parents=True, exist_ok=True)
    imgs[0].save(PREVIEW / "graveyard.gif", save_all=True, append_images=imgs[1:], duration=1000 // FPS, loop=0)
    for i in (0, 20, 30, 40, 100):
        imgs[i].save(PREVIEW / f"graveyard_{i}.png")


if __name__ == "__main__":
    ASSETS.mkdir(parents=True, exist_ok=True)
    rgba = [rasterise(scene, f, W, H) for f in range(FRAMES)]
    write_anim(ASSETS / "graveyard.anim", [rgba_to_bgra(r) for r in rgba], W, H, FPS)
    size = (ASSETS / "graveyard.anim").stat().st_size
    print(f"wrote graveyard.anim ({FRAMES} frames, {size} bytes)")
    preview(rgba)
