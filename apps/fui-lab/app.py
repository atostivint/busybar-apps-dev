#!/usr/bin/env python3
"""FUI Lab: parameterised sci-fi HUD designs for the BUSY Bar, rendered on the computer.

    python app.py --scene scope --cycles 2 --thickness 2 --accent amber
    python app.py --scene gauge --value 72 --segments 12 --host 127.0.0.1:8080     # emulator

The manager starts apps with --host 127.0.0.1:8321 and forwards draws to the bar; every flag below is a form
control in its dashboard, and a variation is a saved set of them. The frames are drawn here (the bar's
JavaScript is far too slow for that), packed into one looping .anim, uploaded once and played by the firmware,
so after the first draw this app sends nothing. Changing a parameter means restarting (the manager does it
when you switch variation); renders are cached by parameters in assets/.

Preview without the bar:    python -m fui.preview --scene scope --cycles 2 --out preview.png
"""
import json
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from fui.cli import build_parser, given_params
from fui.render import build

APP = "fui-lab"
ASSETS = Path(__file__).resolve().parent / "assets"


def call(base, path, method="GET", body=None, raw=None, ctype="application/json", timeout=5):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(base + path, data=data, method=method, headers={"Content-Type": ctype} if data else {})
    with urllib.request.urlopen(req, timeout=timeout):
        pass


def upload(base, name):
    q = urllib.parse.urlencode({"application_name": APP, "file": name})
    data = (ASSETS / name).read_bytes()
    for attempt in range(5):  # 508 = asset briefly locked by the display, 408 = slow upload
        try:
            call(base, "/api/assets/upload?" + q, "POST", raw=data, ctype="application/octet-stream", timeout=60)
            return
        except urllib.error.HTTPError as e:
            if e.code in (408, 508) and attempt < 4:
                time.sleep(0.5 + attempt)
                continue
            raise


def clear(base):
    """Wipe this app's elements; the manager hard-kills apps on Windows, so `finally` may never run."""
    try:
        call(base, "/api/display/draw?" + urllib.parse.urlencode({"application_name": APP}), "DELETE")
    except (urllib.error.URLError, OSError):
        pass


def main():
    a = build_parser("FUI Lab: parameterised HUD designs, rendered on the computer").parse_args()
    base = "http://" + a.host.replace("http://", "").rstrip("/")
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    clear(base)
    name = build(ASSETS, a.scene, given_params(a), a.accent, a.loop, a.fps, a.min_alpha)
    element = {"id": "fui", "type": "animation", "path": name, "x": 0, "y": 0, "loop": True}
    uploaded = False
    try:
        while True:
            try:
                if not uploaded:
                    upload(base, name)
                    uploaded = True
                call(base, "/api/display/draw", "POST", body={"application_name": APP, "priority": a.priority, "elements": [element]})
                break
            except urllib.error.HTTPError as e:
                if e.code != 409:  # 409 = another app has the screen; keep trying
                    print(f"draw failed: HTTP {e.code}", file=sys.stderr)
            except (urllib.error.URLError, OSError) as e:
                print(f"cannot reach {base}: {e}", file=sys.stderr)
            time.sleep(2)
        while True:  # the firmware loops the animation; this process only keeps the app alive
            time.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        clear(base)


if __name__ == "__main__":
    main()
