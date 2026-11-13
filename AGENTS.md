# BUSY Bar apps dev

BUSY Bar setup (Windows), 2026-10-31

- Manager: `C:\Users\elekt\bin\busybar-manager` (clone of maxswinkels/busybar-manager),
  dashboard http://127.0.0.1:8321. Start: `BUSYBAR_PYTHON=python node server.js`
  (`python3` is the Store stub on Windows). No autostart yet.
- This repo = private `atostivint/busybar-apps-dev` (branch `master`), registered in the
  manager's `appsDirs` (use forward slashes). Apps: `hello-bar` (starter),
  `halloween-clock` (styles: `graveyard` default, `classic`).
- halloween-clock (graveyard style) is built from stacked `.anim` layers, bottom to top:
  `moon_<kind>`, `sky_<weather>`, `moonrim_<kind>` (outline above the clouds), `scenery`,
  and for foggy `mist_foggy`; then the time text; then one-shot events (bat, thunder, charge).
  Weather (calm/stormy/foggy) and moon (full/half/crescent/blood) are random at startup and
  every `--reroll` minutes unless fixed with `--weather` / `--moon`. Thunder only in stormy and
  foggy, plus a strike at every new hour there. A strike turns the clock electric green and sweeps its hue back (24 s)
  to orange: the app reads the digit pixels from `/api/screen`, writes a fade `.anim` shaped like
  them (`charge_*.anim`, git-ignored) and uploads it; a second overlay (`glowcharge_*.anim`, between scenery and time) turns the orange glow behind the clock green too, and both flicker with the two bolts.
- Assets are generated: `python tools/gen_halloween.py` (pumpkin/bat, classic style),
  `python tools/gen_graveyard.py` (everything graveyard, ~2 min; deletes old `graveyard*.anim`).
  Restart the app after regenerating (it uploads the files at startup):
  `POST http://127.0.0.1:8321/api/_manager/apps/halloween-clock/restart`. The app is blank for
  ~20 s while it uploads. App log: `GET /api/_manager/apps/halloween-clock/log`.
- Sky loops are 300 frames = 15 s, which divides 60 s on purpose (see gotcha 5).

## Where the apps actually run (2026-11-13)

- `prochain-ter` (and `fui-clock`) do not run from the local manager above: they run on the k3s
  manager, dashboard `https://busybar.homelab.lan` (self-signed certificate, so `curl -k`).
  Namespace `busybar`, deployment `busybar-manager`; apps live on the `busybar-apps` PVC mounted
  at `/app/apps/<slug>` in the pod, each with a `.busybar-library.json` stamp naming the repo and
  commit it was installed from.
- Deploy = push `master`, refresh the catalog, update that app (config and variation are kept, and
  the app is restarted if it was running):
  `curl -k -X POST https://busybar.homelab.lan/api/_manager/library/check -H 'Content-Type: application/json' -d '{}'`
  then `curl -k -X POST https://busybar.homelab.lan/api/_manager/library/update -H 'Content-Type: application/json' -d '{"slug":"prochain-ter"}'`.
  (PowerShell: send the JSON from a file with `--data-binary "@body.json"`, inline escaping breaks.)
- Do not hand-copy files into the pod with `kubectl cp` any more: the stamp keeps pointing at an
  older commit, and the pod then runs a patch no commit describes. That is how the 12/11 clock
  patch (47cd896) got to the pod without the stamp following it.
- Inspect it: `kubectl -n busybar exec deploy/busybar-manager -- sh -c 'grep -n "def clock" -A7 /app/apps/prochain-ter/board.py'`;
  app log `GET /api/_manager/apps/prochain-ter/log`; screen capture `GET /api/screen?display=0` on
  the same host (base64 of 72x16 pixels, 3 bytes each, BGR).
- The bar is the same device for both managers: `barHost` 192.168.59.122 (`token` in the configs).
- prochain-ter's desk clock puts both facts on one screen, far apart: the train's departure time
  (bright) and destination (muted) on the left at `RX` (the exact place the departure time takes on
  every other screen), and the current time alone in the top right corner, muted
  (`_text("now", ..., 71, -1, th["sub"], align="top_right")`). The block and logo stay on the left
  like everywhere else. The owner asked for the left on 12/11, then for this two-times layout on
  13/11 — leave it that way unless he says otherwise.

## Gotchas

1. `npm run build` fails with `EALLOWSCRIPTS` because `~/.npmrc` has `allow-scripts`;
   build with `NPM_CONFIG_USERCONFIG` pointing to an empty file.
2. On Windows the manager hard-kills apps, so `finally:` never runs; every app must
   `DELETE /api/display/draw?application_name=...` at startup.
3. A 409 low-priority on draw = another client holds the screen. The manager also 409s a
   draw from a second `application_name`, so test with the app's own name.
4. A draw with a single changed element (new time text, new color) makes the bar stop rendering
   the text once the scene has heavy animations (HTTP 200, digits gone) until every element is
   drawn again. So the app redraws all elements at every minute change and for every event.
5. A redraw restarts all looping animations (verified), so keep loops at 60 s / n.
6. Element z-order = array order within one draw; an element sent alone lands behind the rest.
   Events are sent together with the whole scene, last, so the bat flies in front of the time.
7. Big uploads can time out (HTTP 408; sky_foggy / mist are ~200 KB): `upload()` retries.

## Verification and config

- Verify on the real display by capturing `/api/screen?display=0` via the manager proxy
  (127.0.0.1:8321); the skill's `templates/screenshot.py` does this.
- Bar host + token live in the manager's `config.json`, not in the repo.
- Skill installed: `~/.Codex/skills/busybar`.

## Open item

- The time glow is a blurred haze, not digit-shaped; ask the user if it looks good.
