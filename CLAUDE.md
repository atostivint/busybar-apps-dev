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
- Skill installed: `~/.claude/skills/busybar`.

## Open item

- The time glow is a blurred haze, not digit-shaped; ask the user if it looks good.

## macOS / USB setup and jam-intro (merged from ~/BusyBar, 2026-10-31)

- Second machine: MacBook, bar plugged in over USB. Over USB the bar is always at
  `http://10.0.4.20` and needs no token; Wi-Fi needs the HTTP API enabled on the bar and the key in
  `BUSYBAR_TOKEN` (never on the command line, never committed). The bar documents its own API at
  `http://10.0.4.20/docs`. If nothing answers: unplug, replug, wait 5 s.
- `apps/jam-intro` (stunfest/octojam jam stand) is stdlib-only Python. `run-jam-intro.command`
  (bash) is a launcher around `app.py`; `jam-intro.applescript` builds a double-clickable app
  (`osacompile -o "$HOME/Jam Intro.app" jam-intro.applescript`).
- `pool` effect: lettering is drawn pixel by pixel from hand-made fonts (8x11 bold, 5x7 fallback)
  because downscaling the festival artwork made 72x16 unreadable. The Stunfest logo is traced from
  `logo-source-stunfest-nb.svg` with a 3 px climb. Wheel / wheel click / start-pause are read from the
  bar's `/api/status/ws` WebSocket (`Controls`, protobuf `State`; ping it or the bar drops it after ~10 s).
- Same-name asset re-upload too soon fails because the bar locks an asset while a draw reads it;
  `Sender` rotates through a few filenames.
- Pre-rendered loops: `python3 tools/jam-loop/build.py stunfest 6 15` writes
  `<name>_72x16.anim` (needs Pillow; 1 s cross-fade makes the seam seamless). Copy into
  `apps/jam-intro/loops/`; `app.py` plays `loops/<title>_72x16.anim` and uploads it once.
- Firmware 1.2.4 bug seen on macOS: joining Wi-Fi (web UI, `POST /api/wifi/connect`, or phone app)
  freezes the HTTP API on USB and Wi-Fi (ping still works). Recovery: forget the network on the bar
  and restart it (Start/Pause + Back, 3 s). Related upstream issues: busy-app/busybar-firmware
  #1042, #949, #896, #940. Prefer USB for jams.
- Logos belong to the association 3 Hit Combo (personal / jam use only).
