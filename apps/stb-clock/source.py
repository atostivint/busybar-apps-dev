"""The button images: downloaded once, then served from a local cache.

Nothing from taylor.fyi/buttons lives in this repository. `assets/buttons.txt` lists the file names
the app wants; on startup `ensure()` downloads whatever is missing into `cache/buttons/` and the app
reads the images from there. The cache survives restarts and works offline, and deleting the folder
simply makes the next start download everything again.
"""
import urllib.error
import urllib.request
from pathlib import Path

SITE = "https://taylor.fyi/buttons"
UA = "busybar-stb-clock/1.1 (+personal desk display)"


def names(list_file):
    """The wanted file names, one per line; '#' starts a comment, blank lines are ignored."""
    out = []
    for line in Path(list_file).read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def ensure(folder, wanted, log=print):
    """Download the missing images into `folder`; returns (folder, kept names, failures).

    A failed download is logged and skipped: the app keeps working with what the cache already has.
    Files that are already there are never fetched again.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    have, failed = [], []
    todo = [n for n in wanted if not (folder / n).exists()]
    for i, name in enumerate(todo, 1):
        try:
            (folder / name).write_bytes(_get(f"{SITE}/files/{name}"))
            if i % 20 == 0 or i == len(todo):
                log(f"buttons: {i}/{len(todo)} downloaded")
        except (urllib.error.URLError, OSError, ValueError) as e:
            failed.append(name)
            log(f"buttons: could not download {name}: {e}")
    for name in wanted:
        if (folder / name).exists():
            have.append(name)
    return folder, have, failed
