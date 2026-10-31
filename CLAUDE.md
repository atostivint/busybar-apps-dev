# BUSY Bar apps dev

BUSY Bar setup (Windows), 2026-10-31

- Manager: `C:\Users\elekt\bin\busybar-manager` (clone of maxswinkels/busybar-manager),
  dashboard http://127.0.0.1:8321. Start: `BUSYBAR_PYTHON=python node server.js`
  (`python3` is the Store stub on Windows). No autostart yet.
- This repo = private `atostivint/busybar-apps-dev` (branch `master`), registered in the
  manager's `appsDirs` (use forward slashes). Apps: `hello-bar` (starter),
  `halloween-clock` (styles: `graveyard` default, `classic`).
- halloween-clock assets are generated: `python tools/gen_halloween.py` (pumpkin/bat),
  `python tools/gen_graveyard.py` (scene, 4 bat flights, thunder). Restart the app after
  regenerating, since it uploads the `.anim` files at startup. Random bat/thunder are
  triggered by the app; the time text is re-sent after each event to stay on top.

## Gotchas

1. `npm run build` fails with `EALLOWSCRIPTS` because `~/.npmrc` has `allow-scripts`;
   build with `NPM_CONFIG_USERCONFIG` pointing to an empty file.
2. On Windows the manager hard-kills apps, so `finally:` never runs; every app must
   `DELETE /api/display/draw?application_name=...` at startup.
3. A 409 low-priority on draw = another client holds the screen.

## Verification and config

- Verify on the real display by capturing `/api/screen?display=0` via the manager proxy
  (127.0.0.1:8321); the skill's `templates/screenshot.py` does this.
- Bar host + token live in the manager's `config.json`, not in the repo.
- Skill installed: `~/.claude/skills/busybar`.

## Open item

- The time glow is a blurred haze, not digit-shaped; ask the user if it looks good.
