#!/usr/bin/env python3
"""Graveyard night scene for the Halloween clock.

    python tools/gen_graveyard.py

Writes into apps/halloween-clock/assets/:
  graveyard.anim                        looping base scene: tree, pumpkin, moon, drifting clouds,
                                        stars, grass and a breathing glow behind the time
  bat_{lr,rl}_{high,low}.anim           one-shot bat flights (direction x altitude)
  thunder.anim                          one-shot lightning: sky flash + bolt from the clouds

The base scene loops (120 frames = 6 s). The bat and thunder are played by the app
at random times, because a baked loop cannot be random. The middle of the bar
(x 18..54, rows 3..12) is kept free of scenery; the app draws the time on top.
Also writes tools/preview/*.gif|png (a 10x LED-style preview, without the time digits).
"""
import math

from gen_halloween import ASSETS, FPS, PREVIEW, bat, flicker, inside, lerp, rasterise, scale
from make_anim import rgba_to_bgra, write_anim

W, H = 72, 16
SCENE_FRAMES = 120   # 6 s loop; every periodic effect below divides 120
BAT_FRAMES = 60      # 3 s flight
THUNDER_FRAMES = 16  # 0.8 s


def seg_dist(x, y, a, b):
    ax, ay, bx, by = *a, *b
    dx, dy = bx - ax, by - ay
    k = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - (ax + k * dx), y - (ay + k * dy))


# ---- base scene layers (each returns a colour or None) ---------------------------------

def ground(x, y, f):
    if y >= 15.1:
        return (30, 62, 26)
    if int(y) == 14 and int(x) in (2, 9, 20, 27, 33, 41, 49, 52, 60, 66):
        return (38, 85, 32)
    return None


def tombstones(x, y, f):
    grey = (88, 94, 112)
    if 55 <= x <= 58.6 and 12.4 <= y <= 15.2:
        return grey
    if ((x - 56.8) / 1.8) ** 2 + ((y - 12.4) / 1.6) ** 2 <= 1 and y < 12.4:
        return grey
    if 61.3 <= x <= 64.1 and 12.8 <= y <= 15.2 and not (y < 13.4 and x > 63.0):
        return scale(grey, 0.85)
    if (68.1 <= x <= 69.3 and 10.4 <= y <= 15.2) or (66.8 <= x <= 70.6 and 11.7 <= y <= 12.9):
        return scale(grey, 0.9)
    return None


def moon(x, y, f):
    if math.hypot(x - 63.6, y - 4.6) <= 4.1 and math.hypot(x - 66.2, y - 3.4) > 3.5:
        return (225, 215, 150)
    return None


CLOUD = (34, 39, 60)
CLOUD_RIM = (66, 74, 104)  # edge lit by the moon


def cloud_hit(x, y, cx, cy, s=1.0):
    """Union of three puffs on a flat base; returns a distance-like value < 1 when inside."""
    best = 9.0
    for dx, dy, r in ((-2.4, 0.5, 1.9), (0.1, -0.3, 2.4), (2.5, 0.6, 1.8)):
        d = math.hypot((x - cx - dx * s), (y - cy - dy * s)) / (r * s)
        best = min(best, d)
    if abs(x - cx) <= 3.9 * s and cy + 0.4 * s <= y <= cy + 1.9 * s:
        best = min(best, 0.8)
    return best


def clouds(x, y, f):
    p = 2 * math.pi * f / SCENE_FRAMES
    # (centre x, centre y, scale): drift back and forth so the moon is covered and uncovered
    for cx, cy, s in ((61.0 + 5.0 * math.sin(p), 2.4, 0.62),
                      (66.5 - 4.0 * math.sin(p + 1.1), 7.0, 0.55),
                      (57.0 + 2.0 * math.sin(p + 2.4), 0.8, 0.45)):
        d = cloud_hit(x, y, cx, cy, s)
        if d <= 1.0:
            return CLOUD_RIM if d > 0.72 and y < cy + 1.2 * s else CLOUD
    return None


def tree(x, y, f):
    brown = (96, 56, 26)
    sw = math.sin(2 * math.pi * f / 60)
    if inside([(4.0, 15.4), (5.0, 9.0), (6.2, 9.0), (7.2, 15.4)], x, y):
        return brown
    base = (5.6, 9.2)
    tip_up, tip_r, tip_l = (5.0 + 0.8 * sw, 1.8), (10.6 + 0.8 * sw, 4.2), (1.6 + 0.7 * sw, 4.6)
    pt = lambda a, b, k: (a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k)
    twigs = [
        (base, tip_up, 1.0), (base, tip_r, 1.0), (base, tip_l, 1.0),
        (pt(base, tip_r, 0.55), (12.2 + 1.0 * sw, 6.8), 0.8),
        (pt(base, tip_up, 0.55), (2.8 + 1.0 * sw, 2.4), 0.8),
        (pt(base, tip_l, 0.55), (0.4 + 0.8 * sw, 7.0), 0.8),
    ]
    return brown if any(seg_dist(x, y, a, b) <= w / 2 for a, b, w in twigs) else None


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
            return scale((165, 185, 255), 0.35 + 0.35 * math.sin(2 * math.pi * (f + ph) / 40))
    return None


# Glow behind the time: soft orange haze peaking behind the digits and fading outward.
GLOW_C, GLOW_HALF = (36.0, 7.9), (15.0, 4.4)


def time_glow(x, y, f):
    breathe = 0.5 + 0.5 * math.sin(2 * math.pi * f / 60 - 1.0)   # 3 s breath, 0..1
    dx, dy = max(abs(x - GLOW_C[0]) - GLOW_HALF[0], 0), max(abs(y - GLOW_C[1]) - GLOW_HALF[1], 0)
    d = math.hypot(dx, dy)
    level = (0.10 + 0.14 * breathe) * math.exp(-((d / 3.4) ** 2))
    return scale((255, 100, 0), level) if level > 0.025 else None


SCENE_LAYERS = [tree, mini_pumpkin, tombstones, clouds, moon, ground, stars, time_glow]  # first hit wins


def scene(x, y, f):
    for layer in SCENE_LAYERS:
        c = layer(x, y, f)
        if c:
            return c
    return None


# ---- one-shot overlays --------------------------------------------------------------------

def bat_flight(direction, low):
    """direction +1 left->right, -1 right->left; low flies near the ground."""
    def shape(x, y, f):
        u = f / (BAT_FRAMES - 1)
        cx = (-7 + 86 * u) if direction > 0 else (79 - 86 * u)
        cy = (10.2 - 2.6 * math.sin(math.pi * u)) if low else (6.5 - 4.2 * math.sin(math.pi * u))
        s = 0.7
        return bat(8 + (x - cx) / s, 8.6 + (y - cy) / s, f)
    return shape


BOLT = [(62.6, 4.2), (61.2, 7.0), (63.2, 8.4), (60.4, 11.0), (61.6, 12.4), (58.4, 15.6)]
# (sky flash alpha, bolt visible) per frame: strike, flicker, second strike, fade
THUNDER = [(0.34, True), (0.30, True), (0.04, False), (0.06, False), (0.46, True), (0.46, True),
           (0.30, True), (0.20, False), (0.14, False), (0.10, False), (0.07, False), (0.05, False),
           (0.03, False), (0.02, False), (0.0, False), (0.0, False)]


def thunder(x, y, f):
    wash, bolt = THUNDER[f]
    if bolt and any(seg_dist(x, y, BOLT[i], BOLT[i + 1]) <= 0.62 for i in range(len(BOLT) - 1)):
        return (240, 248, 255, 255)
    if wash > 0:
        return (175, 195, 255, round(255 * wash * 0.28))
    return None


# ---- output ---------------------------------------------------------------------------------

def build(name, shape, frames):
    rgba = [rasterise(shape, f, W, H) for f in range(frames)]
    write_anim(ASSETS / f"{name}.anim", [rgba_to_bgra(r) for r in rgba], W, H, FPS)
    size = (ASSETS / f"{name}.anim").stat().st_size
    print(f"wrote {name}.anim ({frames} frames, {size // 1024} KiB)")
    return rgba


def image(rgba, base=None, cell=10):
    """LED-style PIL image of one frame, optionally composited over another RGBA frame."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (W * cell, H * cell), (14, 14, 16))
    d = ImageDraw.Draw(img)
    for y in range(H):
        for x in range(W):
            i = (y * W + x) * 4
            r, g, b = 0, 0, 0
            lit = False
            for layer in (base, rgba):
                if layer is None:
                    continue
                lr, lg, lb, la = layer[i:i + 4]
                if la:
                    k = la / 255
                    r, g, b, lit = round(r * (1 - k) + lr * k), round(g * (1 - k) + lg * k), round(b * (1 - k) + lb * k), True
            d.ellipse([x * cell + 1, y * cell + 1, x * cell + cell - 2, y * cell + cell - 2],
                      fill=(r, g, b) if lit else (30, 30, 34))
    return img


def previews(scene_rgba, bat_rgba, thunder_rgba):
    PREVIEW.mkdir(parents=True, exist_ok=True)
    frames = [image(r) for r in scene_rgba]
    frames[0].save(PREVIEW / "graveyard.gif", save_all=True, append_images=frames[1:], duration=1000 // FPS, loop=0)
    from PIL import Image
    rows = [image(thunder_rgba[i], scene_rgba[10]) for i in (0, 2, 4, 7)] + \
           [image(bat_rgba[i], scene_rgba[10]) for i in (8, 30)]
    strip = Image.new("RGB", (W * 10, H * 10 * len(rows)))
    for k, im in enumerate(rows):
        strip.paste(im, (0, k * H * 10))
    strip.save(PREVIEW / "events_strip.png")
    for i in (0, 30, 60, 90):
        frames[i].save(PREVIEW / f"graveyard_{i}.png")


if __name__ == "__main__":
    ASSETS.mkdir(parents=True, exist_ok=True)
    scene_rgba = build("graveyard", scene, SCENE_FRAMES)
    bats = {}
    for name, direction, low in (("bat_lr_high", 1, False), ("bat_rl_high", -1, False),
                                 ("bat_lr_low", 1, True), ("bat_rl_low", -1, True)):
        bats[name] = build(name, bat_flight(direction, low), BAT_FRAMES)
    thunder_rgba = build("thunder", thunder, THUNDER_FRAMES)
    previews(scene_rgba, bats["bat_rl_low"], thunder_rgba)
