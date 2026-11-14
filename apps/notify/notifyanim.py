#!/usr/bin/env python3
"""The notification pictures: one 26x16 looping .anim per kind, no Pillow (see anim.py).

They fill the 26x16 block on the left of the alert screen, so every pixel is written opaque over
the block colour: the icon is the block's ink, the file carries the theme's colours baked in (one
set of files per theme, like car.py).

Each icon is hand-drawn here as a small ASCII grid, then animated in one of two ways:
    a frame sequence  "seq": four hand-drawn walk frames, played as-is at the kind's own "fps"
    a motion          bob: the figure breathes up and down, the edge split over two rows
                      pulse: the ink brightens and dims, the block colour untouched
                      blink: the ink is on for half the loop and nearly off for the other (alarm)

The 1 s loop (12 frames at 12 fps) divides 60 s, so a redraw on the minute does not visibly restart
it (CLAUDE.md gotcha 5). The walk cycles are 4 frames at 10 fps: 0.4 s, which also divides 60 s.

    python notifyanim.py --out cache --theme day
"""
import argparse
import math
from pathlib import Path

import anim
import board

W, H = 26, 16  # the block
FPS, FRAMES = 12, 12  # 1 s loop, which divides 60 s
BOB = 0.85  # pixels of travel: the edge splits over two rows, so it reads as a breath, not a jump
SHADE = 2  # of board.LEVELS: how far the edge colour sits from the ink toward the block
PULSE = 3  # how far the ink dims toward the block at the bottom of a pulse
BLINK = 3  # how far the ink dims at the dark half of a blink (half the way to the block colour)

# --- the icons --------------------------------------------------------------------------------
# "I" ink, "S" edge (a shade between the ink and the block), anything else is block colour. Rows
# of one sprite must all be the same width; the sprite is centred in the block.

# A 4-frame walk cycle: contact / passing / contact / passing, 10 fps (100 ms a frame, from the
# pixel-art-animator skill) — a 0.4 s loop, which divides 60 s. Every frame is 16 rows tall on the
# same canvas, so _layer() pins it at y=0 and both feet always reach row 15: the sprite never bobs
# between frames (layer-pixel-art: same canvas, one shared ground line). "I" is the near side and
# "S" the far one, so the leg swap reads although the stride itself is symmetric. Hard pixels only,
# no edge coverage.

PERSON_WALK = [
    [  # 1: near (right) foot forward, near arm back, far arm forward
        ".....III.....",
        "....IIIII....",
        "....II.II....",
        "....IIIII....",
        ".....III.....",
        "....IIIII....",
        ".II.IIIII.SS.",
        "....IIIII....",
        "....IIIII....",
        "....ISSSI....",
        "....IIIII....",
        "....SS.II....",
        "....SS..II...",
        "....SS...II..",
        "...SS.....II.",
        "...SS.....II.",
    ],
    [  # 2: passing, feet together, arms down through the swing
        ".....III.....",
        "....IIIII....",
        "....II.II....",
        "....IIIII....",
        ".....III.....",
        "....IIIII....",
        "....IIIII....",
        "....IIIII....",
        ".II.IIIII.SS.",
        "....ISSSI....",
        "....IIIII....",
        ".....SSII....",
        ".....SSII....",
        ".....SSII....",
        ".....SSII....",
        ".....SSII....",
    ],
    [  # 3: near foot back, near arm forward, far arm back
        ".....III.....",
        "....IIIII....",
        "....II.II....",
        "....IIIII....",
        ".....III.....",
        "....IIIII....",
        ".SS.IIIII.II.",
        "....IIIII....",
        "....IIIII....",
        "....ISSSI....",
        "....IIIII....",
        "....II.SS....",
        "...II..SS....",
        "..II...SS....",
        ".II.....SS...",
        ".II.....SS...",
    ],
    [  # 4: passing again, arms swapped
        ".....III.....",
        "....IIIII....",
        "....II.II....",
        "....IIIII....",
        ".....III.....",
        "....IIIII....",
        "....IIIII....",
        "....IIIII....",
        ".SS.IIIII.II.",
        "....ISSSI....",
        "....IIIII....",
        ".....SSII....",
        ".....SSII....",
        ".....SSII....",
        ".....SSII....",
        ".....SSII....",
    ],
]

# The same character carrying a parcel in front: the parcel is held with the near arm, so that arm
# no longer swings; the far arm does, at three heights, which keeps the four frames distinct.
# Same 4 frames, same ground line, wider canvas (15) to fit the parcel.

DELIVERY_WALK = [
    [  # 1: near foot forward, far arm high
        ".....III.......",
        "....IIIII......",
        "....II.II......",
        "....IIIII......",
        ".....III.......",
        "....IIIII.IIII.",
        ".SS.IIIII.ISSI.",
        "....IIIII.ISSI.",
        "....IIIII.IIII.",
        "....ISSSI......",
        "....IIIII......",
        "....SS.II......",
        "....SS..II.....",
        "....SS...II....",
        "...SS.....II...",
        "...SS.....II...",
    ],
    [  # 2: passing, far arm low
        ".....III.......",
        "....IIIII......",
        "....II.II......",
        "....IIIII......",
        ".....III.......",
        "....IIIII.IIII.",
        "....IIIII.ISSI.",
        "....IIIII.ISSI.",
        ".SS.IIIII.IIII.",
        "....ISSSI......",
        "....IIIII......",
        ".....SSII......",
        ".....SSII......",
        ".....SSII......",
        ".....SSII......",
        ".....SSII......",
    ],
    [  # 3: near foot back, far arm high again
        ".....III.......",
        "....IIIII......",
        "....II.II......",
        "....IIIII......",
        ".....III.......",
        "....IIIII.IIII.",
        ".SS.IIIII.ISSI.",
        "....IIIII.ISSI.",
        "....IIIII.IIII.",
        "....ISSSI......",
        "....IIIII......",
        "....II.SS......",
        "...II..SS......",
        "..II...SS......",
        ".II.....SS.....",
        ".II.....SS.....",
    ],
    [  # 4: passing, far arm at mid swing
        ".....III.......",
        "....IIIII......",
        "....II.II......",
        "....IIIII......",
        ".....III.......",
        "....IIIII.IIII.",
        "....IIIII.ISSI.",
        ".SS.IIIII.ISSI.",
        "....IIIII.IIII.",
        "....ISSSI......",
        "....IIIII......",
        ".....SSII......",
        ".....SSII......",
        ".....SSII......",
        ".....SSII......",
        ".....SSII......",
    ],
]

PACKAGE = [  # a parcel, the tape left as block colour through the box
    "IIIIIIIIIIIII",
    "IIIIIIIIIIIII",
    "IIIII...IIIII",
    "IIIII...IIIII",
    "IIIII...IIIII",
    "IIIII...IIIII",
    "IIIII...IIIII",
    "IIIII...IIIII",
    "IIIIIIIIIIIII",
]

ANIMAL = [  # a face with two ears, eyes and a muzzle as block-colour holes
    ".I.........I.",
    ".II.......II.",
    ".III.....III.",
    ".IIIIIIIIIII.",
    "IIIIIIIIIIIII",
    "IIIIIIIIIIIII",
    "II..IIIII..II",
    "IIIIIIIIIIIII",
    "IIIIIIIIIIIII",
    ".IIII...IIII.",
    "..IIIIIIIII..",
    "...IIIIIII...",
]

VEHICLE = [  # a van, side view: roof, body, two wheels
    ".....IIIIIII.....",
    "....IIIIIIIII....",
    "...IIIIIIIIIII...",
    "..IIIIIIIIIIIII..",
    ".IIIIIIIIIIIIIII.",
    ".IIIIIIIIIIIIIII.",
    "..IIIIIIIIIIIII..",
    ".IIIII.....IIIII.",
    "..III.......III..",
]

HEATPUMP = [  # the outdoor unit's fan: a wheel with blades
    "...IIIIIII...",
    "..IIIIIIIII..",
    ".IIII...IIII.",
    ".III.....III.",
    "IIII..I..IIII",
    "III..III..III",
    "III.IIIII.III",
    "III..III..III",
    "IIII..I..IIII",
    ".III.....III.",
    ".IIII...IIII.",
    "..IIIIIIIII..",
    "...IIIIIII...",
]

THERMO = [  # a thermometer: a tube with tick marks, the bulb at the bottom
    ".....ISI.....",
    ".....ISI.....",
    "..II.ISI.II..",
    ".....ISI.....",
    "..II.ISI.II..",
    ".....ISI.....",
    "..II.ISI.II..",
    ".....ISI.....",
    "...IIIIIII...",
    "..IISSSSSII..",
    "..ISSSSSSSI..",
    "..ISSSSSSSI..",
    "...IISSSII...",
    "....IIIII....",
]

GENERIC = [  # a bell: the fallback for a kind this app does not know
    "......I......",
    ".....III.....",
    "....IIIII....",
    "...IIIIIII...",
    "..IIIIIIIII..",
    "..IIIIIIIII..",
    "..IIIIIIIII..",
    "..IIIIIIIII..",
    ".IIIIIIIIIII.",
    "IIIIIIIIIIIII",
    ".IIIIIIIIIII.",
    "....IIIII....",
]

# kind -> the file it is written to, its picture and its motion. An entry with "seq" is a frame
# sequence played as-is (hard pixels, no motion) at its own "fps"; the rest keep "rows"+"motion".
KINDS = {
    "person": {"file": "person.anim", "seq": PERSON_WALK, "fps": 10},
    "delivery": {"file": "delivery.anim", "seq": DELIVERY_WALK, "fps": 10},
    "package": {"file": "package.anim", "rows": PACKAGE, "motion": "pulse"},
    "animal": {"file": "animal.anim", "rows": ANIMAL, "motion": "bob"},
    "vehicle": {"file": "vehicle.anim", "rows": VEHICLE, "motion": "pulse"},
    "heatpump": {"file": "heatpump.anim", "rows": HEATPUMP, "motion": "blink"},
    "bc250": {"file": "bc250.anim", "rows": THERMO, "motion": "pulse"},
    "generic": {"file": "generic.anim", "rows": GENERIC, "motion": "pulse"},
}

# What Home Assistant puts in `kind` -> one of KINDS. Matched case- and space-insensitively; "_"
# and "-" count as spaces, so "alarme_hp" and "Alarme HP" land on the same key.
ALIASES = {
    "personne": "person", "personnes": "person", "une personne": "person",
    "plusieurs personnes": "person", "personne detectee": "person", "presence": "person",
    "livreur": "delivery", "livreurs": "delivery", "livraison": "delivery",
    "colis": "package", "paquet": "package",
    "chat": "animal", "chien": "animal", "renard": "animal", "oiseau": "animal", "biche": "animal",
    "animal": "animal", "animaux": "animal",
    "vehicule": "vehicle", "vehicules": "vehicle", "voiture": "vehicle", "camion": "vehicle",
    "alarme hp": "heatpump", "alarme pac": "heatpump", "pac": "heatpump", "heatpump": "heatpump",
    # the BC-250 GPU temperature alerts (its automations send kind: bc250, but the
    # `verdict.choice` style of title may carry the model or the sensor name instead)
    "bc250": "bc250", "bc 250": "bc250", "gpu": "bc250", "gpu temperature": "bc250",
    "gpu temp": "bc250", "temperature": "bc250", "temp": "bc250", "chaud": "bc250",
    "surchauffe": "bc250", "gpu chaud": "bc250",
    "generic": "generic", "generique": "generic", "defaut": "generic", "default": "generic",
}


def _strip_article(key):
    """Drop one leading article: "un chat" -> "chat", "l'oiseau" -> "oiseau"."""
    for article in ("un ", "une ", "des ", "le ", "la ", "les "):
        if key.startswith(article):
            return " ".join(key[len(article):].split())
    if key.startswith("l'"):
        return " ".join(key[2:].split())
    return key


def _prefix_match(key):
    """The longest ALIASES / KINDS key that is a leading run of whole words in `key`.

    "bc 250 90 c" -> "bc 250", "gpu 91" -> "gpu", "chat noir" -> "chat". Whole words only, so
    "chateau" never matches "chat", and a single-word key with nothing after it is left to the
    exact lookups above.
    """
    words = key.split()
    for n in range(len(words) - 1, 0, -1):
        candidate = " ".join(words[:n])
        if candidate in ALIASES or candidate in KINDS:
            return candidate
    return None


def kind_for(kind):
    """Raw `kind` from the event -> one of KINDS (case/space-insensitive, "_" and "-" as spaces).

    One leading article is ignored too, because the README's automation sends
    `kind: "{{ verdict.choice }}"` and Home Assistant's verdicts read "une personne", "un chat",
    "des colis". A kind that only *starts* with a known name (the BC-250 alerts read
    "BC-250 90 C", "BC-250 85 C !") matches on its longest leading run of words.
    """
    key = str(kind or "").strip().lower().replace("_", " ").replace("-", " ")
    key = " ".join(key.split())
    if key in ALIASES:
        return ALIASES[key]
    if key in KINDS:
        return key
    bare = _strip_article(key)
    if bare in ALIASES:
        return ALIASES[bare]
    if bare in KINDS:
        return bare
    prefix = _prefix_match(bare)
    if prefix is not None:
        return ALIASES.get(prefix, prefix)
    return "generic"


# --- the renderer -----------------------------------------------------------------------------

def _rgb(color):
    """'#RRGGBBAA' -> (R, G, B)."""
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def _blend(c1, c2, k):
    """c1 -> c2 by k (0..1, clamped)."""
    k = max(0.0, min(1.0, k))
    return tuple(round(a + (b - a) * k) for a, b in zip(c1, c2))


def _put(px, x, y, rgb, alpha):
    i = (y * W + x) * 4
    px[i], px[i + 1], px[i + 2], px[i + 3] = rgb[0], rgb[1], rgb[2], alpha


def _layer(rows):
    """The sprite as a grid of "I"/"S"/None, centred in the block."""
    assert len({len(r) for r in rows}) == 1, "every row of a sprite must be the same width"
    assert len(rows[0]) <= W and len(rows) <= H, "sprite larger than the block"
    x0, y0 = (W - len(rows[0])) // 2, (H - len(rows)) // 2
    grid = [[None] * W for _ in range(H)]
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            if ch in "IS":
                grid[y0 + r][x0 + c] = ch
    return grid


def _flat(rows, block, on_block):
    """One frame of a hand-drawn sequence: every sprite pixel at full coverage, hard edges.

    No bob and no pulse here: a sequence carries its own motion, and the frames of a walk must
    share one ground line, which any vertical motion would break.
    """
    grid = _layer(rows)
    bg, ink, shade = _rgb(block), _rgb(on_block), _rgb(board._mix(on_block, block, SHADE))
    px = bytearray(W * H * 4)
    for y in range(H):
        for x in range(W):
            ch = grid[y][x]
            _put(px, x, y, ink if ch == "I" else shade if ch == "S" else bg, 255)
    return bytes(px)


def frames(key, block, on_block):
    """The frames, RGBA bytes each: pass them through anim.rgba_to_bgra() to anim.write_anim().
    block/on_block are the theme colours of the colour block and of the ink drawn on it.

    A kind with "seq" gives one hard-edged frame per grid, in order, with no motion; the others
    give FRAMES frames of their motion (bob / pulse / blink), exactly as before.
    """
    spec = KINDS[key]
    if "seq" in spec:
        return [_flat(rows, block, on_block) for rows in spec["seq"]]
    grid, motion = _layer(spec["rows"]), spec["motion"]
    bg = _rgb(block)
    out = []
    for f in range(FRAMES):
        phase = 0.5 - 0.5 * math.cos(2 * math.pi * f / FRAMES)  # 0 -> 1 -> 0, one breath per loop
        bob = BOB * phase if motion == "bob" else 0.0
        if motion == "pulse":
            dim = PULSE * phase
        elif motion == "blink":
            dim = 0.0 if phase >= 0.5 else BLINK
        else:
            dim = 0.0
        ink = _rgb(board._mix(on_block, block, min(board.LEVELS, dim)))
        shade = _rgb(board._mix(on_block, block, min(board.LEVELS, SHADE + dim)))
        cover = {"I": [[0.0] * W for _ in range(H)], "S": [[0.0] * W for _ in range(H)]}
        for y in range(H):
            for x in range(W):
                ch = grid[y][x]
                if ch is None:
                    continue
                cover[ch][y][x] += 1.0 - bob  # the bob splits a row over two rows
                if bob and y + 1 < H:
                    cover[ch][y + 1][x] += bob
        px = bytearray(W * H * 4)
        for y in range(H):
            for x in range(W):
                rgb = bg
                if cover["S"][y][x]:
                    rgb = _blend(rgb, shade, cover["S"][y][x])
                if cover["I"][y][x]:
                    rgb = _blend(rgb, ink, cover["I"][y][x])
                _put(px, x, y, rgb, 255)  # opaque: the file replaces the whole block
        out.append(bytes(px))
    return out


def fps_for(key):
    """The fps this kind's file is written at (a sequence may carry its own)."""
    return KINDS[key].get("fps", FPS)


def frames_in(key):
    """How many frames this kind's file has."""
    spec = KINDS[key]
    return len(spec["seq"]) if "seq" in spec else FRAMES


def write(key, path, block, on_block):
    """Writes that kind's .anim for those theme colours."""
    anim.write_anim(path, [anim.rgba_to_bgra(f) for f in frames(key, block, on_block)], W, H, fps_for(key))
    return path


def write_all(outdir, theme="day"):
    """Writes every kind -> {kind key: local path}."""
    th = board.THEMES[theme]
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    return {key: str(write(key, out / spec["file"], th["block"], th["on_block"]))
            for key, spec in KINDS.items()}


def _cli():
    p = argparse.ArgumentParser(description="Write the notification pictures")
    p.add_argument("--out", default="cache", help="output directory")
    p.add_argument("--theme", default="day", choices=sorted(board.THEMES))
    a = p.parse_args()
    for key, path in write_all(a.out, a.theme).items():
        print(f"{key}: {path}")


if __name__ == "__main__":
    _cli()
