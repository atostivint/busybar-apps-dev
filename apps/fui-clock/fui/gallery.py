"""Every design, animated, in one self-contained HTML page - no bar needed.

    python -m fui.gallery --out gallery.html [--design seg --design radar] [--accent amber] [--hour12]

Each card shows eight seconds spanning a minute change (so the odometer rolls and the seconds hands wrap),
rendered by exactly the code that renders the bar's animations.
"""
import base64
import json
import sys
import time
import zlib
from pathlib import Path

from .cli import build_parser
from .designs import DESIGNS, SHAPES
from .render import parse_zones, render_minute

PAGE = Path(__file__).with_name("gallery.html.tpl")


def card_frames(design, E, a, shape=None):
    """RGB bytes for T-4 s .. T+4 s around the minute starting at E."""
    fps = a.fps
    args = (a.accent, a.hour12, not a.steady_colon, parse_zones(a.zones), a.min_alpha, (a.alarm_colour, shape or a.alarm_shape))
    before = render_minute(design, E - 60, fps, *args, first=56 * fps, prev=True)
    after = render_minute(design, E, fps, *args, last=4 * fps, prev=True)
    raw = bytearray()
    for f in before + after:
        for i in range(0, len(f), 4):
            raw += f[i:i + 3] if f[i + 3] else b"\0\0\0"
    return bytes(raw), len(before) + len(after)


def main():
    p = build_parser("Render every clock design into an animated HTML gallery")
    p.add_argument("--out", default="gallery.html")
    p.add_argument("--only", action="append", choices=list(DESIGNS), help="limit to these designs (repeatable)")
    p.add_argument("--at", default="", help="HH:MM to show (default: now)")
    a = p.parse_args()
    now = time.time()
    if a.at:
        hh, mm = (int(v) for v in a.at.split(":"))
        lt = time.localtime(now)
        now = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, hh, mm, 0, 0, 0, -1))
    E = int(now // 60) * 60
    cards = []
    todo = [(n, None) for n in (a.only or DESIGNS)]
    if "alarm" in [n for n, _ in todo]:  # the alarm sign is an option: show every shape
        i = [n for n, _ in todo].index("alarm")
        todo[i:i + 1] = [("alarm", s) for s in SHAPES]
    for name, shape in todo:
        raw, n = card_frames(name, E, a, shape)
        label = name + (f" / {shape}" if shape else "")
        cards.append({"name": label, "desc": DESIGNS[name][1], "n": n, "data": base64.b64encode(zlib.compress(raw, 9)).decode()})
        print(f"  {label}: {n} frames, {len(cards[-1]['data']) // 1024} KB", file=sys.stderr)
    html = PAGE.read_text(encoding="utf-8").replace("/*DATA*/", json.dumps({"fps": a.fps, "cards": cards}))
    Path(a.out).write_text(html, encoding="utf-8")
    print(f"{a.out}: {len(cards)} designs")


if __name__ == "__main__":
    sys.exit(main())
