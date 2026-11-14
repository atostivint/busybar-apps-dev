#!/usr/bin/env python3
"""Notifications: Home Assistant notifications on the BUSY Bar (72x16 front display).

    HA_URL=http://192.168.59.211 HA_TOKEN=... python app.py
    python app.py --hold 20 --snooze-button ok

At rest it draws nothing, so the bar belongs to its other apps. When Home Assistant fires the
`busybar_notify` event it takes the screen for --hold seconds: the animation for the kind, the
title, the message, the current time in a free corner, and the orange notification LED. The bar's
snooze button dismisses it. See the README for the HA side (`action: event.fire`).

The manager starts apps with --host 127.0.0.1:8321 and forwards draws to the bar; it overrides the
draw priority with the variation's, which must be ~90 (above prochain-ter 85 and the bar's clock 80).
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
from collections import deque
from pathlib import Path

import board
import buttons
import haws
import notifyanim

APP = "notify"
PRIORITY = 90  # only used outside the manager: the variation's priority wins there
RETRY_S = 0.5  # seconds between attempts while a draw is refused (409) or the bar is unreachable
HERE = Path(__file__).resolve().parent


def args():
    p = argparse.ArgumentParser(description="Home Assistant notifications on the front display")
    p.add_argument("--host", default="10.0.4.20")
    p.add_argument("--hold", type=float, default=15, help="seconds a notification stays on screen")
    p.add_argument("--snooze-button", default="start", choices=["start", "ok", "back", "off"],
                   help="bar button that dismisses the notification on screen")
    p.add_argument("--anim-dir", default="cache", help="where the generated .anim files are written")
    # no default shown here on purpose: the values come from HA_URL / HA_TOKEN and must not leak into --help
    p.add_argument("--ha-url", default=None, help="Home Assistant URL (default: $HA_URL)")
    p.add_argument("--ha-token", default=None, help="HA long-lived token (default: $HA_TOKEN; prefer the variable)")
    return p.parse_args()


def call(base, path, method="GET", body=None, timeout=5):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def clear(base):
    q = urllib.parse.urlencode({"application_name": APP})
    try:
        call(base, "/api/display/draw?" + q, "DELETE")
    except (urllib.error.URLError, OSError):
        pass


def draw(base, elements, led=None):
    """-> True when the bar took the draw, False when it refused it (409, another app holds the
    screen) or could not be reached. The caller must not forget the screen on a failure: with the
    variation priority left at 10 every draw is refused, and the alert would be lost."""
    body = {"application_name": APP, "priority": PRIORITY, "elements": elements}
    if led:
        body["led_notification_color"] = led
    try:
        call(base, "/api/display/draw", "POST", body)
        return True
    except urllib.error.HTTPError as e:
        if e.code != 409:
            print(f"draw failed: HTTP {e.code} {e.read()[:200]!r}", file=sys.stderr, flush=True)
        elif time.time() - draw.last409 > 30:  # 409 = another app holds the screen; keep trying
            draw.last409 = time.time()
            print(f"draw refused (409): {e.read()[:120]!r}", file=sys.stderr, flush=True)
        return False
    except (urllib.error.URLError, OSError) as e:
        print(f"cannot reach {base}: {e}", file=sys.stderr, flush=True)
        return False


draw.last409 = 0.0


def remove(base, ids):
    """Elements persist by id: drop the ones the new screen no longer has."""
    if not ids:
        return
    try:
        call(base, "/api/display/draw", "DELETE", {"application_name": APP, "element_ids": sorted(ids)})
    except (urllib.error.URLError, OSError):
        pass


def upload(base, local, remote, timeout=30):
    q = urllib.parse.urlencode({"application_name": APP, "file": remote})
    req = urllib.request.Request(f"{base}/api/assets/upload?{q}", data=Path(local).read_bytes(), method="POST",
                                 headers={"Content-Type": "application/octet-stream"})
    return urllib.request.urlopen(req, timeout=timeout).read()


def prepare_anims(base, outdir):
    """Write every kind's .anim and upload each once (the firmware loops it, no redraw per frame).
    -> {kind key: remote name}; a kind whose upload failed is missing and falls back to the "!"."""
    remotes = {}
    for key, local in notifyanim.write_all(outdir, "day").items():
        remote = f"notify-{key}.anim"
        for attempt in range(5):  # 408 = the upload timed out, 508 = the asset is briefly locked
            try:
                upload(base, local, remote)
                remotes[key] = remote
                break
            except urllib.error.HTTPError as e:
                if e.code not in (408, 508) or attempt == 4:
                    print(f"{key} animation upload failed, using the static block: {e}", file=sys.stderr, flush=True)
                    break
                time.sleep(0.5 + attempt)
            except (urllib.error.URLError, OSError) as e:
                print(f"{key} animation upload failed, using the static block: {e}", file=sys.stderr, flush=True)
                break
    return remotes


def main():
    a = args()
    base = "http://" + a.host.replace("http://", "").rstrip("/")
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    clear(base)  # a hard kill (Windows) skips `finally`; wipe leftovers from a previous run

    outdir = Path(a.anim_dir)
    if not outdir.is_absolute():
        outdir = HERE / outdir

    cfg = haws.config(a.ha_url, a.ha_token)  # checked before the uploads: a misconfigured run exits
    if not cfg:                             # before it writes and uploads seven files for nothing
        raise SystemExit("set HA_URL and HA_TOKEN (or --ha-url / --ha-token): there is nothing to listen to")

    remotes = prepare_anims(base, outdir)

    pending = deque()  # the listener thread appends, the loop drains: only the last one is shown

    def on_event(data):
        event = haws.parse_event(data)
        if event is None:
            print("event: ignored, the payload is not an object", file=sys.stderr, flush=True)
            return
        pending.append(event)
        print(f"event: {notifyanim.kind_for(event['kind'])} / {board.ascii_fold(event['title'])}",
              file=sys.stderr, flush=True)

    ha = haws.HAWebSocket(on_event, *cfg).start()
    pad = buttons.Buttons(a.host, a.snooze_button) if a.snooze_button != "off" else None

    current, shown_until, dirty = None, 0.0, False
    shown_ids, shown_minute, cleared = set(), None, True
    next_try = 0.0  # a refused draw is retried at most 1/RETRY_S times a second
    try:
        while True:
            while pending:  # a new event: it replaces whatever is on screen and restarts the hold
                current, shown_until, dirty = pending.popleft(), time.time() + a.hold, True
            if current is not None and time.time() < shown_until:
                hhmm = time.strftime("%H:%M")
                # Redraw on the minute only: a redraw restarts the animation (CLAUDE.md gotcha 5),
                # and the corner clock is the only thing that changed. A refused draw is retried a
                # few times a second until it lands: `dirty` only clears once it did.
                if (dirty or hhmm != shown_minute) and time.time() >= next_try:
                    els = board.alert("day", current["kind"], current["title"], current["message"], hhmm,
                                      remotes.get(notifyanim.kind_for(current["kind"])),
                                      source=current.get("source", ""))
                    if draw(base, els, board.LED_ALERT):
                        ids = {e["id"] for e in els}
                        remove(base, shown_ids - ids)
                        shown_ids, shown_minute, dirty, cleared = ids, hhmm, False, False
                    else:
                        next_try = time.time() + RETRY_S
                if pad is not None and pad.pressed():  # snooze: dismiss it now
                    current, shown_until, dirty = None, 0.0, False
                time.sleep(0.2)
                continue
            if not cleared:  # nothing to show: hand the screen back to the other apps, once
                clear(base)
                current, shown_ids, shown_minute, cleared = None, set(), None, True
            if pad is not None:
                pad.pressed()  # drain presses made while idle: they must not dismiss the next alert
            time.sleep(0.3)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        ha.stop()
        clear(base)


if __name__ == "__main__":
    main()
