"""The button images: downloaded once, then served from a local cache.

Nothing from taylor.fyi/buttons lives in this repository. `assets/buttons.txt` lists the file names
the app wants; on startup `ensure()` downloads whatever is missing into `cache/buttons/` and the app
reads the images from there. The cache survives restarts and works offline, and deleting the folder
simply makes the next start download everything again.

`follow()` keeps the rotation current: it compares the site's index (`buttons-data.js`) with the
copy taken at the previous check and returns the files that appeared since, so a button added to the
collection shows up on the bar without anyone touching the repository.
"""
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SITE = "https://taylor.fyi/buttons"
INDEX = f"{SITE}/buttons-data.js"
UA = "busybar-stb-clock/1.2 (+personal desk display)"


def names(list_file):
    """The wanted file names, one per line; '#' starts a comment, blank lines are ignored."""
    out = []
    for line in Path(list_file).read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def read_names(list_file):
    """`names()`, but a missing file is simply an empty list."""
    path = Path(list_file)
    return names(path) if path.exists() else []


def write_names(list_file, wanted):
    """One file name per line, so the app carries its own state between runs."""
    Path(list_file).write_text("".join(n + "\n" for n in wanted), encoding="utf-8")


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def site_index(timeout=20):
    """Every file name the collection page lists, in page order (the site's own index)."""
    js = _get(INDEX, timeout).decode("utf-8", "replace")
    return re.findall(r'"([^"]+)"', js)


def _url(name):
    return f"{SITE}/files/{urllib.parse.quote(name)}"


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
            (folder / name).write_bytes(_get(_url(name)))
            if i % 20 == 0 or i == len(todo):
                log(f"buttons: {i}/{len(todo)} downloaded")
        except (urllib.error.URLError, OSError, ValueError) as e:
            failed.append(name)
            log(f"buttons: could not download {name}: {e}")
    for name in wanted:
        if (folder / name).exists():
            have.append(name)
    return folder, have, failed


def follow(state, wanted, log=print):
    """Merge the files that appeared on the site since the last check; returns (wanted, fresh).

    `state/index.txt` holds the site's index as of the last check, so everything in the live index
    that is missing from it is new. The very first check only records a baseline: the collection
    already lists thousands of buttons, and downloading all of them is not what "new" means.
    """
    state = Path(state)
    state.mkdir(parents=True, exist_ok=True)
    seen_path = state / "index.txt"
    try:
        live = site_index()
    except (urllib.error.URLError, OSError, ValueError) as e:
        log(f"buttons: site check skipped ({e})")
        return wanted, []
    if len(live) < 100:            # a 404 page or a broken script, not a shrunken collection
        log("buttons: site check skipped (the index looks broken)")
        return wanted, []
    if not seen_path.exists():
        write_names(seen_path, live)
        log(f"buttons: {len(live)} on the site, baseline recorded")
        return wanted, []
    known = set(read_names(seen_path))
    fresh = [n for n in live if n not in known]
    write_names(seen_path, live)
    if fresh:
        picked = set(wanted)
        wanted = wanted + [n for n in fresh if n not in picked]
        log(f"buttons: {len(fresh)} new on the site ({', '.join(fresh[:6])}"
            f"{' ...' if len(fresh) > 6 else ''})")
    return wanted, fresh
