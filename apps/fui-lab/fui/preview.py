"""Renders a scene to an LED-style PNG strip without touching the bar.

    python -m fui.preview --scene scope --cycles 2 --thickness 2 --out strip.png [--frames 8]

Takes the same flags as app.py. Frames are evenly spread over one loop and stacked top to bottom.
"""
import struct
import sys
import zlib
from pathlib import Path

from .cli import build_parser, given_params
from .render import frames, params_for
from .scenes import SCENES

CELL, DOT = 6, 5


def write_png(path, rows, width, height):
    raw = b"".join(b"\0" + bytes(r) for r in rows)

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def main():
    p = build_parser("Preview a FUI Lab scene as a PNG strip")
    p.add_argument("--out", default="preview.png")
    p.add_argument("--frames", type=int, default=8, help="frames to show, spread over one loop")
    a = p.parse_args()
    loop = a.loop or SCENES[a.scene]["loop"]
    params = params_for(a.scene, given_params(a))
    all_frames = frames(a.scene, params, a.accent, loop, a.fps, a.min_alpha)
    picks = [all_frames[int(i * len(all_frames) / a.frames)] for i in range(a.frames)]
    pad = 2
    gap = [10, 10, 12]
    rows = []
    for frame in picks:
        for y in range(16):
            band = []
            for x in range(72):
                r, g, b, al = frame[(y * 72 + x) * 4:(y * 72 + x) * 4 + 4]
                band += ([r, g, b] if al else [30, 30, 34]) * DOT + gap * (CELL - DOT)
            rows += [band] * DOT + [gap * (72 * CELL)] * (CELL - DOT)
        rows += [[60, 60, 70] * (72 * CELL)] * pad
    write_png(a.out, rows, 72 * CELL, len(rows))
    print(f"{a.out}: scene {a.scene}, loop {loop}s, {len(all_frames)} frames, params {params}")


if __name__ == "__main__":
    sys.exit(main())
