#!/usr/bin/env python3
"""Renders the app off the bar: one still PNG and a GIF of several buttons, from the same layout code.

    python tools/preview.py                          # preview.png + preview.gif
    python tools/preview.py --time 09:41 --start 20
    python tools/preview.py --count 10 --scale 8

The still is the first badge at 6x (nearest neighbour, one LED = one block). The GIF shows `--count`
badges for one second each, which is what the bar does every `--hold` seconds. Files land next to
app.py.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

import belt
import layout
import source

HERE = Path(__file__).resolve().parent.parent
CACHE = HERE / "cache" / "buttons"


def image(c, scale):
    size = (c.w * scale, c.h * scale)
    return Image.frombytes("RGB", (c.w, c.h), bytes(c.buf)).resize(size, Image.NEAREST)


def main():
    p = argparse.ArgumentParser(description="One whole classic web button at a time, with the time")
    p.add_argument("--hold", type=int, default=10, help="seconds each button stays on screen")
    p.add_argument("--clock", default="auto", choices=("auto",) + layout.CORNERS,
                   help="clock corner: auto = emptiest readable spot")
    p.add_argument("--outline", default="off", choices=("on", "off"),
                   help="force the halo around the digits")
    p.add_argument("--clock-color", default="auto", choices=("inverse", "auto"),
                   help="digit colour: black/white or inverse")
    p.add_argument("--clock-style", default="filled", choices=("filled", "outline"),
                   help="digits: filled or hollow outline")
    p.add_argument("--start", type=int, default=0, help="badge index to start on")
    p.add_argument("--time", default=time.strftime("%H:%M"), help="HH:MM to show")
    p.add_argument("--scale", type=int, default=6, help="pixel size in the images (default 6)")
    p.add_argument("--out", default="preview", help="output name without extension")
    p.add_argument("--count", type=int, default=6, help="badges in the GIF (default 6)")
    a = p.parse_args()

    hh, mm = (int(v) for v in a.time.split(":"))
    if not (0 <= hh < 24 and 0 <= mm < 60):
        sys.exit(f"--time must be HH:MM, got {a.time!r}")
    hhmm = f"{hh:02d}:{mm:02d}"

    source.ensure(CACHE, source.names(HERE / "assets" / "buttons.txt"))
    badges = belt.load(CACHE)
    if not badges:
        sys.exit("no usable buttons in cache/buttons")
    n = len(badges)
    start = max(0, min(n - 1, a.start))
    scale = max(1, a.scale)
    out = HERE / a.out

    state = {"corner": a.clock if a.clock != "auto" else None}

    def corner_for(badge):
        if a.clock != "auto":
            return a.clock
        state["corner"] = layout.choose_corner(badge, hhmm, state["corner"])
        return state["corner"]

    def render(badge):
        corner = corner_for(badge)
        align = layout.choose_align(badge, corner, hhmm)
        plate = layout.needs_plate(badge, corner, hhmm, align)
        outline = not plate and (a.outline == "on" or layout.needs_outline(badge, corner, hhmm, align))
        return layout.frame_canvas(badge, hhmm, corner, a.clock_color, outline, plate, align,
                                   a.clock_style)

    first = badges[start]
    image(render(first), scale).save(out.with_suffix(".png"))

    count = max(1, min(n, a.count))
    frames, names = [], []
    for k in range(count):
        badge = badges[(start + k) % n]
        names.append(badge.name)
        frame = render(badge)
        frames.append(image(frame, scale).convert("P", palette=Image.ADAPTIVE, colors=64))
    frames[0].save(out.with_suffix(".gif"), save_all=True, append_images=frames[1:],
                   duration=1000, loop=0, optimize=True)

    print(f"{n} badges at {badges[0].w}x{badges[0].h}, one every {a.hold} s")
    print(f"{out.with_suffix('.png')}: {first.name} at {scale}x")
    print(f"{out.with_suffix('.gif')}: {', '.join(names)}")


if __name__ == "__main__":
    main()
