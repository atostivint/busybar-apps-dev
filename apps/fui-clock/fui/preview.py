"""Writes preview.gif: a tour of some designs on a drawn 72x16 LED panel (README and library thumbnail).

    python -m fui.preview [--out preview.gif]

Needs Pillow (only this script does; the app itself is stdlib-only).
"""
import argparse
import time

from PIL import Image, ImageDraw

from .canvas import H, W
from .cli import colour
from .canvas import RED
from .render import parse_zones, render_minute

CELL, SS = 10, 4          # px per LED in the output, supersampling for round dots
FPS = 10
SECONDS = 2.2             # per design
# (design, accent, alarm colour, second of the minute to start from)
TOUR = [("seg", "cyan", 8), ("radar", "green", 8), ("matrix", "amber", 20), ("perimeter", "cyan", 2),
        ("glitch", "magenta", 14), ("holo", "cyan", 4), ("odometer", "white", 57), ("world", "green", 10),
        ("alarm", "red", 6), ("spectrum", "cyan", 6), ("warp", "cyan", 6), ("monolith", "orange", 6),
        ("rain", "green", 6), ("target", "amber", 6)]


def led_panel(rgba):
    """RGBA frame -> a PIL image of round LEDs on a dark panel."""
    big = CELL * SS
    img = Image.new("RGB", (W * big, H * big), (10, 10, 12))
    d = ImageDraw.Draw(img)
    r = big * 0.40
    for y in range(H):
        for x in range(W):
            i = (y * W + x) * 4
            r_, g, b, a = rgba[i:i + 4]
            c = (r_, g, b) if a else (30, 30, 34)
            cx, cy = (x + 0.5) * big, (y + 0.5) * big
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=c)
    return img.resize((W * CELL, H * CELL), Image.LANCZOS)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="preview.gif")
    a = p.parse_args()
    t = time.localtime()
    E = int(time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 10, 10, 0, 0, 0, -1)))
    zones = parse_zones("NYC=America/New_York,TYO=Asia/Tokyo,SYD=Australia/Sydney")
    images = []
    for design, accent, sec in TOUR:
        first = int(sec * FPS)
        frames = render_minute(design, E, FPS, colour(accent), False, True, zones, 0.25, (RED, "triangle"),
                               first=first, last=first + int(SECONDS * FPS), prev=True)
        images += [led_panel(f) for f in frames]
        print(design, flush=True)
    per = int(SECONDS * FPS)  # the palette comes from a sample of every design, or the colours of later ones are lost
    sample = Image.new("RGB", (images[0].width, images[0].height * len(TOUR)))
    for k in range(len(TOUR)):
        sample.paste(images[k * per + per // 2], (0, k * images[0].height))
    pal = sample.quantize(colors=96, method=Image.Quantize.MEDIANCUT)
    frames = [im.quantize(palette=pal, dither=Image.Dither.NONE) for im in images]
    frames[0].save(a.out, save_all=True, append_images=frames[1:], duration=1000 // FPS, loop=0, optimize=True)


if __name__ == "__main__":
    main()
