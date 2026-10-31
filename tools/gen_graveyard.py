#!/usr/bin/env python3
"""Graveyard night scene for the Halloween clock.

    python tools/gen_graveyard.py

Writes into apps/halloween-clock/assets/ (the app stacks them: moon, sky, scenery, mist):
  moon_{full,half,crescent,blood}.anim  the moon and its halo (20 frames, static)
  moonrim_{...}.anim                    thin outline of the moon disc, drawn above the sky
  sky_{calm,stormy,foggy}.anim          weather: clouds, stars or fog (300 frames = 15 s loop)
  scenery.anim                          tree, pumpkin, tombstones, grass, glow behind the time (120 frames)
  mist_foggy.anim                       ground fog drawn in front of the scenery
  bat_{lr,rl}_{high,low}.anim           one-shot bat flights (direction x altitude)
  thunder.anim                          one-shot lightning: sky flash + bolt (stormy and foggy only)

The bat and thunder are played by the app
at random times, because a baked loop cannot be random. The middle of the bar
(x 18..54, rows 3..12) is kept free of scenery; the app draws the time on top.
Also writes tools/preview/*.gif|png (a 10x LED-style preview, without the time digits).
"""
import math

from gen_halloween import ASSETS, FPS, PREVIEW, bat, flicker, inside, lerp, rasterise, scale
from make_anim import rgba_to_bgra, write_anim

W, H = 72, 16
SCENE_FRAMES = 300   # 15 s loop (slow cloud drift); divides 60 s, see app.py; every periodic effect divides 300
BAT_FRAMES = 60      # 3 s flight
THUNDER_FRAMES = 16  # 0.8 s


def seg_dist(x, y, a, b):
    ax, ay, bx, by = *a, *b
    dx, dy = bx - ax, by - ay
    k = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - (ax + k * dx), y - (ay + k * dy))


# ---- base scene layers (each returns a colour or None) ---------------------------------

def ground(x, y, f):
    """Rolling hills: grass surface at a varying height, with darker earth below."""
    top = 14.0 + 0.55 * math.sin(x / 5.5 + 0.8) + 0.45 * math.sin(x / 2.3 + 2.0)
    if y < top:
        return None
    if y < top + 1.0:
        shade = 0.85 + 0.25 * math.sin(x * 1.7)          # uneven blades of grass
        return scale((38, 88, 34), shade)
    return scale((24, 44, 22), 0.9 + 0.2 * math.sin(x * 0.9 + y))


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


# ---- moon (own layer, drawn first so the sky can cover it) -------------------------------------

MOON_C = (63.6, 4.6)
MOONS = {  # kind -> (disc radius, halo colour, halo strength)
    "full": (3.7, (130, 150, 210), 0.30),
    "half": (3.9, (120, 140, 200), 0.24),
    "crescent": (4.1, (120, 140, 200), 0.22),
    "blood": (3.7, (170, 40, 30), 0.30),
}


def moon_layer(kind):
    radius, halo, strength = MOONS[kind]

    def shape(x, y, f):
        d = math.hypot(x - MOON_C[0], y - MOON_C[1])
        if d <= radius:
            if kind == "full":
                crater = any(math.hypot(x - cx, y - cy) < r for cx, cy, r in ((62.4, 3.6, 0.8), (65.0, 5.8, 0.9), (63.6, 6.4, 0.5)))
                return (214, 206, 150) if crater else (236, 228, 168)
            if kind == "half":      # right half lit, with a soft terminator
                return (232, 224, 160) if x >= MOON_C[0] - 0.2 else (60, 64, 88)
            if kind == "crescent":
                return (225, 215, 150) if math.hypot(x - 66.2, y - 3.4) > 3.5 else None
            lit = 0.8 + 0.2 * max(0.0, (MOON_C[0] - x + MOON_C[1] - y) / 6.0)   # blood moon
            return scale((190, 42, 26), min(lit, 1.0))
        level = strength * math.exp(-(((d - radius) / 3.2) ** 2))
        return (*halo, round(255 * level)) if level > 0.04 else None
    return shape


def moon_rim(kind):
    """Thin ring round the whole disc, drawn above the clouds so the shape stays readable
    (for a crescent or half moon it also outlines the dark side)."""
    radius = MOONS[kind][0]
    col = (205, 70, 45) if kind == "blood" else (214, 212, 190)

    def shape(x, y, f):
        d = math.hypot(x - MOON_C[0], y - MOON_C[1])
        return (*col, 215) if abs(d - (radius + 0.4)) <= 0.5 else None
    return shape


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


# ---- weather: the sky layer (clouds, stars, fog), drawn above the moon ---------------------------

CLOUD = (34, 39, 60)
CLOUD_RIM = (66, 74, 104)  # edge lit by the moon
STORM = (20, 23, 38)
STORM_RIM = (46, 52, 78)


MOON_THROUGH_CLOUD = 120  # cloud alpha (of 255) over the moon: it shows through, like behind thin cloud


def cloud_hit(x, y, cx, cy, s=1.0):
    """Union of three puffs on a flat base; returns a distance-like value < 1 when inside."""
    best = 9.0
    for dx, dy, r in ((-2.4, 0.5, 1.9), (0.1, -0.3, 2.4), (2.5, 0.6, 1.8)):
        d = math.hypot((x - cx - dx * s), (y - cy - dy * s)) / (r * s)
        best = min(best, d)
    if abs(x - cx) <= 3.9 * s and cy + 0.4 * s <= y <= cy + 1.9 * s:
        best = min(best, 0.8)
    return best


def drifting_clouds(specs, col=CLOUD, rim=CLOUD_RIM):
    """specs: (centre x, centre y, scale, drift amplitude, phase). They sway slowly back and forth."""
    def shape(x, y, f):
        p = 2 * math.pi * f / SCENE_FRAMES
        for cx, cy, s, amp, ph in specs:
            c = cx + amp * math.sin(p + ph)
            d = cloud_hit(x, y, c, cy, s)
            if d <= 1.0:
                c = rim if d > 0.72 and y < cy + 1.2 * s else col
                # in front of the moon a cloud is thin: the moon shows through it, dimmed
                return (*c, MOON_THROUGH_CLOUD) if math.hypot(x - MOON_C[0], y - MOON_C[1]) < 5.0 else c
        return None
    return shape


def cloud_bank(puffs, col=CLOUD, rim=CLOUD_RIM, shade=0.85):
    """Low overcast: puffs (centre x, centre y, radius, phase) that shift a little; lit near the moon."""
    def shape(x, y, f):
        p = 2 * math.pi * f / SCENE_FRAMES
        for cx, cy, r, ph in puffs:
            dx, dy = x - (cx + 1.6 * math.sin(p + ph)), y - (cy + 0.4 * math.sin(2 * p + ph))
            if math.hypot(dx, dy * 1.5) <= r:
                near = math.hypot(x - MOON_C[0], y - MOON_C[1])
                lit = max(0.0, 1.0 - near / 16.0)
                c = scale(lerp(col, rim, lit if dy < 0 else lit * 0.4), shade)
                return (*c, MOON_THROUGH_CLOUD) if near < 5.2 else c   # thin cloud in front of the moon
        return None
    return shape


# the middle of the bar (x 18..54, rows 3..12) stays free: that is where the time is drawn
BANK_LIGHT = [(-2, 1, 3.4, 0.0), (5, 0, 3.0, 1.2), (12, 1, 3.6, 2.1), (20, 0, 3.2, 3.0), (28, 1, 3.4, 4.0),
              (36, 0, 3.0, 5.1), (44, 1, 3.6, 0.7), (51, 0, 3.0, 1.9), (57, 1, 3.2, 2.8),
              (3, 6, 2.4, 3.6), (9, 5, 2.0, 4.6), (57, 7, 2.0, 5.5)]
BANK_STORM = [(-1, 1, 4.2, 0.0), (6, 0, 4.0, 1.2), (13, 1, 4.4, 2.1), (21, 0, 4.0, 3.0), (29, 1, 4.2, 4.0),
              (37, 0, 4.0, 5.1), (45, 1, 4.4, 0.7), (52, 0, 4.0, 1.9), (58, 1, 4.2, 2.8), (66, 0, 4.2, 3.9),
              (72, 1, 4.0, 0.3), (2, 5, 3.4, 3.6), (9, 4, 3.0, 4.6), (15, 6, 2.4, 1.1), (58, 6, 2.8, 5.5),
              (53, 8, 2.2, 2.2), (70, 8, 2.4, 0.9)]

# A few faint stars in the gaps; a slow, shallow twinkle (one 15 s cycle).
STARS = [(16, 3, 0), (13, 7, 30), (17, 10, 60), (2, 10, 90), (8, 3, 45), (56, 2, 15), (58, 10, 75),
         (59, 6, 105), (69, 9, 20), (70, 1, 50), (6, 1, 150), (24, 1, 210), (33, 0, 270), (47, 2, 330)]


def stars(x, y, f):
    cx, cy = int(x), int(y)
    for sx, sy, ph in STARS:
        if (sx, sy) == (cx, cy):
            return scale((150, 170, 230), 0.36 + 0.09 * math.sin(2 * math.pi * (f + ph) / SCENE_FRAMES))
    return None


def haze(x, y, f):
    """Foggy sky: a pale veil that thickens toward the ground and drifts slowly."""
    wave = 0.5 + 0.5 * math.sin(2 * math.pi * (x / 36 - f / SCENE_FRAMES) + y / 3)
    level = (0.10 + 0.12 * y / 16) * (0.6 + 0.4 * wave)
    return (92, 104, 132, round(255 * level))


def mist(x, y, f):
    """Foggy ground mist, drawn in front of the scenery: slow drifting banks near the grass."""
    n = math.sin(2 * math.pi * (x / 18 - f / SCENE_FRAMES))
    m = math.sin(2 * math.pi * (x / 27 + f / SCENE_FRAMES) + 0.3 + y / 4)
    base = max(0.0, min(1.0, (y - 7.0) / 8.0)) ** 1.3 * 0.42
    level = base * (0.55 + 0.25 * n + 0.2 * m)
    return (150, 160, 184, round(255 * level)) if level > 0.03 else None


def stack(*layers):
    def shape(x, y, f):
        for layer in layers:
            c = layer(x, y, f)
            if c:
                return c
        return None
    return shape


MAIN_CLOUDS = [(63.0, 2.6, 1.0, 3.0, 0.0), (65.5, 7.6, 0.9, -2.8, 1.1), (59.5, 0.6, 0.75, 1.5, 2.4)]
WEATHER = {  # name -> (sky layer, optional mist layer drawn above the scenery, thunder?)
    "calm": (stack(drifting_clouds([(58.0, 1.4, 0.6, 4.0, 0.0)]), stars), None, False),
    "stormy": (stack(drifting_clouds([(63.0, 2.6, 1.2, 3.0, 0.0), (65.5, 7.8, 1.0, -2.8, 1.1)], STORM, STORM_RIM),
                     cloud_bank(BANK_STORM, STORM, STORM_RIM, 1.0)), None, True),
    "foggy": (stack(drifting_clouds(MAIN_CLOUDS), cloud_bank(BANK_LIGHT), haze), mist, True),
}


# Glow behind the time: soft orange haze peaking behind the digits and fading outward.
GLOW_C, GLOW_HALF = (36.0, 7.9), (15.0, 4.4)


def time_glow(x, y, f):
    breathe = 0.5 + 0.5 * math.sin(2 * math.pi * f / 60 - 1.0)   # 3 s breath, 0..1
    dx, dy = max(abs(x - GLOW_C[0]) - GLOW_HALF[0], 0), max(abs(y - GLOW_C[1]) - GLOW_HALF[1], 0)
    d = math.hypot(dx, dy)
    level = (0.10 + 0.14 * breathe) * math.exp(-((d / 3.4) ** 2))
    return scale((255, 100, 0), level) if level > 0.025 else None


SCENERY_FRAMES = 120  # lcm of the tree sway (60), pumpkin flicker (40) and glow breath (60)
scenery = stack(tree, mini_pumpkin, tombstones, ground, time_glow)


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


def composite(layers, f):
    """Stack RGBA frames (each layer loops on its own length) into one RGBA frame."""
    out = bytearray(W * H * 4)
    for frames in layers:
        src = frames[f % len(frames)]
        for i in range(0, len(src), 4):
            a = src[i + 3]
            if not a:
                continue
            k, oa = a / 255, out[i + 3] / 255
            na = k + oa * (1 - k)
            for c in range(3):
                out[i + c] = round((src[i + c] * k + out[i + c] * oa * (1 - k)) / na)
            out[i + 3] = round(na * 255)
    return bytes(out)


def previews(layers_by_weather, moons, rims, bat_rgba, thunder_rgba):
    from PIL import Image
    PREVIEW.mkdir(parents=True, exist_ok=True)
    for old in PREVIEW.glob("*"):
        old.unlink()
    for weather, layers in layers_by_weather.items():
        frames = [image(composite(layers, f)) for f in range(0, SCENE_FRAMES, 6)]
        frames[0].save(PREVIEW / f"{weather}.gif", save_all=True, append_images=frames[1:], duration=300, loop=0)
        strip = Image.new("RGB", (W * 10, H * 10 * 3))
        for k, f in enumerate((0, 120, 240)):
            strip.paste(image(composite(layers, f)), (0, k * H * 10))
        strip.save(PREVIEW / f"{weather}_strip.png")
    calm = layers_by_weather["calm"]
    strip = Image.new("RGB", (W * 10, H * 10 * len(moons)))
    for k, kind in enumerate(moons):
        strip.paste(image(composite([moons[kind], calm[1], rims[kind], calm[3]], 0)), (0, k * H * 10))
    strip.save(PREVIEW / "moons_strip.png")
    base = composite(layers_by_weather["stormy"], 0)
    rows = [image(thunder_rgba[i], base) for i in (0, 2, 4, 7)] + [image(bat_rgba[i], base) for i in (8, 30)]
    strip = Image.new("RGB", (W * 10, H * 10 * len(rows)))
    for k, im in enumerate(rows):
        strip.paste(im, (0, k * H * 10))
    strip.save(PREVIEW / "events_strip.png")


if __name__ == "__main__":
    ASSETS.mkdir(parents=True, exist_ok=True)
    for old in ASSETS.glob("graveyard*.anim"):
        old.unlink()  # replaced by the stacked layers below
    moons = {kind: build(f"moon_{kind}", moon_layer(kind), 20) for kind in MOONS}
    rims = {kind: build(f"moonrim_{kind}", moon_rim(kind), 20) for kind in MOONS}
    scenery_rgba = build("scenery", scenery, SCENERY_FRAMES)
    skies = {name: build(f"sky_{name}", sky, SCENE_FRAMES) for name, (sky, _, _) in WEATHER.items()}
    mist_rgba = build("mist_foggy", WEATHER["foggy"][1], SCENE_FRAMES)
    bats = {}
    for name, direction, low in (("bat_lr_high", 1, False), ("bat_rl_high", -1, False),
                                 ("bat_lr_low", 1, True), ("bat_rl_low", -1, True)):
        bats[name] = build(name, bat_flight(direction, low), BAT_FRAMES)
    thunder_rgba = build("thunder", thunder, THUNDER_FRAMES)
    stacks = {w: [moons["full"], skies[w], rims["full"], scenery_rgba] + ([mist_rgba] if w == "foggy" else []) for w in skies}
    previews(stacks, moons, rims, bats["bat_rl_low"], thunder_rgba)
