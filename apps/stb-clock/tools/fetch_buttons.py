#!/usr/bin/env python3
"""Prefetches the button images into the app's cache (the app also does this on its first start).

    python tools/fetch_buttons.py                 # the names in assets/buttons.txt
    python tools/fetch_buttons.py --all           # every image the page lists (a lot)
    python tools/fetch_buttons.py --list mine.txt # your own file names, one per line

The repository ships no button images: `assets/buttons.txt` lists what the app wants, and both this
tool and the app download the missing files into `cache/buttons/` (git-ignored). `--all` needs the
site's index (`buttons-data.js`) and downloads it every time, so it can take a while and is only
meant for filling the cache on purpose.
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import source

HERE = Path(__file__).resolve().parent.parent
CACHE = HERE / "cache" / "buttons"


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--all", action="store_true", help="every image the page lists")
    p.add_argument("--list", help="file with image names (with extension), one per line")
    a = p.parse_args()

    if a.all:
        js = source._get(f"{source.SITE}/buttons-data.js", 30).decode("utf-8", "replace")
        wanted = sorted(set(re.findall(r'"([^"]+)"', js)))
    else:
        names = Path(a.list) if a.list else HERE / "assets" / "buttons.txt"
        wanted = source.names(names)

    folder, have, failed = source.ensure(CACHE, wanted)
    print(f"{len(have)} in {folder}, {len(failed)} failed")
    if failed:
        print("failed:", ", ".join(failed[:10]), "..." if len(failed) > 10 else "")


if __name__ == "__main__":
    main()
