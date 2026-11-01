"""Command-line flags shared by the app and the gallery. The manager shows each flag as a form control."""
import argparse
import re

from .designs import DESIGNS, SHAPES

ACCENTS = {"cyan": "#00E5FF", "amber": "#FFB000", "green": "#3CFF78", "magenta": "#FF46DC", "white": "#FFFFFF",
           "orange": "#FF7A00", "red": "#FF3C28", "yellow": "#FFE600"}
SWATCH = ["cyan", "amber", "green", "magenta", "orange", "white"]  # what a wheel click cycles through
ZONES = "NYC=America/New_York,TYO=Asia/Tokyo,SYD=Australia/Sydney"


def colour(value):
    value = ACCENTS.get(value.lower(), value).strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", value):
        raise argparse.ArgumentTypeError("accent must be RRGGBB or one of " + ", ".join(ACCENTS))
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def build_parser(description):
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--host", default="10.0.4.20")
    p.add_argument("--design", choices=list(DESIGNS) + ["all"], default="seg",
                   help="which clock; 'all' cycles through every design")
    p.add_argument("--rotate", type=int, default=1, help="with --design all: minutes each design stays")
    p.add_argument("--accent", type=colour, default=colour("cyan"),
                   help="colour: cyan, amber, green, magenta, orange, white or RRGGBB")
    p.add_argument("--alarm-colour", type=colour, default=colour("red"), help="alarm design: its colour (same values as --accent)")
    p.add_argument("--alarm-shape", choices=SHAPES, default="triangle", help="alarm design: the warning sign")
    p.add_argument("--no-wheel", action="store_true", help="ignore the wheel (it switches design; a click changes colour)")
    p.add_argument("--hour12", action="store_true", help="12-hour clock")
    p.add_argument("--steady-colon", action="store_true", help="colon does not blink")
    p.add_argument("--zones", default=ZONES, help="world design: LABEL=Area/City pairs, comma separated (3 used)")
    p.add_argument("--min-alpha", type=float, default=0.25,
                   help="brightness floor 0-1 for faint marks (below ~0.25 they vanish on the LEDs)")
    p.add_argument("--fps", type=int, choices=[8, 10, 12, 15], default=10, help="animation frame rate")
    p.add_argument("--priority", type=int, default=80, help="draw priority 1-100 (the bar's own clock outranks 50)")
    return p
