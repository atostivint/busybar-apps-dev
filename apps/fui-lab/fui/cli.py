"""Command-line flags shared by the app and the preview. The manager shows each flag as a form control."""
import argparse
import re

from .scenes import OPTIONS, SCENES

ACCENTS = {"cyan": "#00E5FF", "amber": "#FFB000", "green": "#3CFF78", "magenta": "#FF46DC", "white": "#FFFFFF"}


def colour(value):
    value = ACCENTS.get(value.lower(), value).strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", value):
        raise argparse.ArgumentTypeError("accent must be RRGGBB or one of " + ", ".join(ACCENTS))
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def build_parser(description):
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--host", default="10.0.4.20")
    p.add_argument("--scene", choices=sorted(SCENES), default="scope", help="which design to play")
    p.add_argument("--accent", type=colour, default=colour("cyan"), help="colour: cyan, amber, green, magenta, white or RRGGBB")
    p.add_argument("--min-alpha", type=float, default=0.25,
                   help="brightness floor 0-1 for faint marks (below ~0.25 they vanish on the LEDs)")
    p.add_argument("--loop", type=float, default=0.0, help="loop length in seconds (0 = the scene's own)")
    p.add_argument("--fps", type=int, choices=[10, 12, 15, 20], default=15, help="animation frame rate")
    p.add_argument("--priority", type=int, default=50, help="draw priority 1-100 (default 50)")
    for name, (kind, default, help_) in OPTIONS.items():
        users = [s for s, spec in SCENES.items() if name in spec["opts"]]
        p.add_argument("--" + name.replace("_", "-"), type=kind, default=None, dest=name,
                       help=f"{help_} (default {default}; used by: {', '.join(users)})")
    return p


def given_params(args):
    return {name: getattr(args, name) for name in OPTIONS}
