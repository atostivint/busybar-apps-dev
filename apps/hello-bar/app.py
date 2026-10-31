#!/usr/bin/env python3
"""Hello Bar: minimal starter app for the BUSY Bar (72x16 front display).

    python app.py                              # default message
    python app.py --text "Hi" --color "#00FFAA"
    python app.py --host 127.0.0.1:8080        # emulator

The manager starts apps with --host 127.0.0.1:8321 and forwards draws to the bar.
Every argparse option below becomes a form control in the dashboard.
"""
import argparse
import json
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

APP = "hello-bar"


def args():
    p = argparse.ArgumentParser(description="Hello Bar starter app")
    p.add_argument("--host", default="10.0.4.20")
    p.add_argument("--text", default="HELLO")
    p.add_argument("--color", default="#FFFFFFFF", help="RRGGBBAA with leading #")
    p.add_argument("--interval", type=float, default=1.0, help="seconds between redraws")
    return p.parse_args()


def draw(base, elements):
    body = {"application_name": APP, "elements": elements}
    req = urllib.request.Request(
        base + "/api/display/draw", data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5):
        pass


def clear(base):
    q = urllib.parse.urlencode({"application_name": APP})
    req = urllib.request.Request(base + "/api/display/draw?" + q, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=5):
            pass
    except (urllib.error.URLError, OSError):
        pass  # shutting down; nothing useful to do


def main():
    a = args()
    base = "http://" + a.host.replace("http://", "").rstrip("/")
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        while True:
            try:
                draw(base, [{"id": "0", "type": "text", "text": a.text,
                             "x": 36, "y": 8, "align": "center", "font": "normal",
                             "color": a.color}])
            except urllib.error.HTTPError as e:
                if e.code != 409:  # 409 = another app has higher priority; keep trying
                    print(f"draw failed: HTTP {e.code}", file=sys.stderr)
            except urllib.error.URLError as e:
                print(f"cannot reach {base}: {e.reason}", file=sys.stderr)
            time.sleep(a.interval)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        clear(base)


if __name__ == "__main__":
    main()
