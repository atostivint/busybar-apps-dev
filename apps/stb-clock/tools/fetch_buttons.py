#!/usr/bin/env python3
"""Downloads the classic 88x31 "steal these buttons" from taylor.fyi/buttons into assets/buttons/.

    python tools/fetch_buttons.py                 # the curated wishlist below
    python tools/fetch_buttons.py --list names.txt
    python tools/fetch_buttons.py --all           # every file on the page (a lot)

Only images close to the 88x31 standard are kept (the site also hosts 80x15 chiclets and
other sizes); each one is resized by belt.py at runtime, not here. Files already present are
skipped. The site publishes `buttons-data.js`, a JS array of filenames, and serves images from
files/<name>.
"""
import argparse
import json
import re
import urllib.request
from pathlib import Path

SITE = "https://taylor.fyi/buttons"
OUT = Path(__file__).resolve().parent.parent / "assets" / "buttons"
UA = "busybar-stb-clock/1.0 (+personal desk display)"

WISH = """
firefox firefox02 firefox03 mozilla netscape opera safari ie
wikipedia linux gentoo ubuntu_button mac osx ipod winamp itunes4
myspace livejournal deviantart flickr lastfm digg del.icio.us
wordpress rss xml html401 valid_css xhtml10 php python perl mysql postgresql ruby java javascript
flashplayer photoshop gimp notepad vim_the_editor emacs
kottke zeldman doom3 nintendo gameboybutton snes playstation xbox sonic
simpsons futurama strongbad homestarrunner1 hellokitty totoro
wakeupneo nasa seti redbull dietcoke pepsi starbucks nutella sushi pizza
nirvana radiohead thebeatles ledzeppelin
underconstruction noframes01 web2.0_button poweredby feedburner technorati
paypal ebay google yahoo geocaching flickrbutton
"""


def list_names():
    with urllib.request.urlopen(urllib.request.Request(f"{SITE}/buttons-data.js", headers={"User-Agent": UA}),
                                timeout=30) as r:
        js = r.read().decode("utf-8", "replace")
    return set(re.findall(r'"([^"]+)"', js))


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--list", help="file with one button name (without extension) per line")
    p.add_argument("--all", action="store_true", help="download every image the page lists")
    a = p.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    have = {f.stem for f in OUT.iterdir()} if OUT.exists() else set()

    names = list_names()
    by_stem = {}
    for n in names:
        by_stem.setdefault(Path(n).stem, []).append(n)

    if a.all:
        wanted = sorted(names)
    else:
        wish = Path(a.list).read_text().split() if a.list else WISH.split()
        wanted = []
        for w in wish:
            if w in by_stem:
                wanted += by_stem[w]
            else:
                print(f"  missing on the site: {w}")

    got = []
    for name in sorted(set(wanted)):
        dest = OUT / name
        if name in have:
            continue
        try:
            req = urllib.request.Request(f"{SITE}/files/{name}", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            dest.write_bytes(data)
            got.append(name)
            print(f"  {name:32} {len(data):6} B")
        except Exception as e:
            print(f"  failed {name}: {e}")

    print(f"{len(got)} downloaded, {len(list(OUT.iterdir()))} files in {OUT}")


if __name__ == "__main__":
    main()
