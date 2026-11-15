# Notifications

Home Assistant notifications on the BUSY Bar's 72x16 front display.

The app opens a WebSocket to Home Assistant, authenticates with a long-lived token and subscribes
to the custom event `busybar_notify`. At rest it draws **nothing**, so the bar stays with its other
apps. When an event arrives it takes the screen:

- a 26x16 looping animation in a colour block on the left, chosen by the event's `kind`
  (`person`, `delivery`, `package`, `animal`, `vehicle`, `heatpump`, `bc250`, `generic`; unknown
  kinds fall back to the bell);
- the `source` — the camera or place the event came from — on the top line beside the picture, in
  the readable small font; when the event carries no `source`, its `title` is shown instead;
- the current time, small and muted, on the line below it;
- the orange notification LED (`#FFAA00FF`).

Nothing scrolls and there is no second line: the picture already says what happened (a person, a
parcel, a hot GPU), so the text only has to say *where* and *when*. The `message` an automation may
still send is ignored.

It lets go after `--hold` seconds (15 by default), and the bar's snooze button dismisses it earlier.
A new event simply replaces the one on screen and restarts the hold.

Everything is standard library: no `pip install`, no Pillow.

## Running it

Under the manager (dashboard → this app → Start), the manager starts it with
`--host 127.0.0.1:8321` and forwards the draws to the bar. It reads the token from the
environment, so set `HA_URL` and `HA_TOKEN` for the manager process.

Standalone, against the bar directly:

```
HA_URL=http://192.168.59.211 HA_TOKEN=... python app.py --host 10.0.4.20
python app.py --hold 20 --snooze-button ok
```

| option | default | meaning |
| --- | --- | --- |
| `--host` | `10.0.4.20` | bar, or `127.0.0.1:8321` for the manager |
| `--hold` | `15` | seconds a notification stays on screen |
| `--snooze-button` | `start` | `start`, `ok`, `back` or `off` |
| `--anim-dir` | `cache` | where the generated `.anim` files are written |
| `--ha-url` | `$HA_URL` | Home Assistant URL |
| `--ha-token` | `$HA_TOKEN` | HA long-lived token (prefer the variable: flags show in `ps`) |

## Configuration

- `HA_URL` — this house's Home Assistant is `http://192.168.59.211` on **port 80** (plain HTTP, no
  `:8123`). The WebSocket is `/api/websocket` on the same host and port; the app turns `http://` into
  `ws://` and `https://` into `wss://` itself, so give it the base URL, not the WS one.
- `HA_TOKEN` — a long-lived access token (HA → your profile → Security → Long-lived access tokens).

**The token is never committed.** It lives in the environment (or in the manager's app
configuration, outside this repo); nothing in this directory holds it and the app never prints it —
its log lines name the host and port only.

## Variation priority: set it to ~90

The manager overrides the `priority` an app draws with **the priority of the variation** it is
started from, and the app's own value (`90`, see `PRIORITY` in `app.py`) only counts when it runs
standalone. A notification has to outrank everything else on the bar:

- prochain-ter draws at **85**,
- the bar's built-in clock wins up to **80**,
- so set this app's variation priority to **~90**.

With the default (10) the alert is silently refused with HTTP 409 and the bar keeps showing whatever
it had.

## How it is built

| file | role |
| --- | --- |
| `app.py` | the loop: hold the alert for `--hold` s, redraw it on the minute, clear once when it ends |
| `haws.py` | Home Assistant WebSocket client (hand-rolled framing, ping every ~20 s, reconnect with backoff) |
| `notifyanim.py` | the pictures: one hand-drawn ASCII sprite per kind, rendered to a 26x16 `.anim` (person and delivery are 4-frame walk cycles at 10 fps) |
| `board.py` | the screen: elements, themes, `ascii_fold()` |
| `anim.py`, `rt.py`, `buttons.py` | copies from `prochain-ter`: the `.anim` writer, the protobuf reader, the button stream |

Load-bearing details, all learned on this bar (see `CLAUDE.md`):

- **ASCII only.** The bar fonts have no accents, so every string goes through `board.ascii_fold()`
  (`é → e`, `’ → '`, `· → -`, `— → -`); anything that is not printable ASCII is dropped.
- **Redraw everything.** A draw that changes a single element makes the digits disappear on an
  animated scene until every element is sent again, so the screen is always one full element list.
- **A redraw restarts the animation**, so the alert is redrawn when it starts and then only when
  the minute flips (the corner clock is all that changes). The animations are 1 s loops, which
  divides 60 s.
- **Clean up at startup**: Windows hard-kills an app, so `finally` never runs and the app begins
  with `DELETE /api/display/draw?application_name=notify`.
- **Uploads retry** on 408 (timeout) and 508 (the asset is briefly locked by the display); a kind
  whose upload failed is drawn as a static "!" in its colour block instead.

## Home Assistant side

Three automations fire the event. The token never appears in any YAML: the event is fired from
inside Home Assistant itself.

**`event.fire` is not a service.** Home Assistant's `event` domain exposes none, so
`action: event.fire` is reported as "unknown action" and stops the automation. The built-in action
is the bare `event:` key with `event_data:` under it, exactly as in the snippets below.

`source` is the short camera or location the screen prints (about nine characters fit; a longer one
is cut with `..`). An event without a `source` shows its `title` instead, so a one-off automation can
keep sending only `kind` + `title`. The `message` is accepted and ignored.

Doorbell:

```yaml
# automation.terrasse_ouest_chat_colis_ou_livreur  (after script.canal)
- event: busybar_notify
  event_data:
    kind: "{{ verdict.choice }}"
    source: "TER OUEST"
    title: "Terrasse Ouest · {{ verdict.choice }}"
    message: "{{ verdict.choice }} sur la terrasse ouest · confiance {{ (verdict.confidence * 100) | round(0) }} %"
```

Heat-pump automation `automation.alarme_hp_dimplex` — at the top of its `actions` (before the 16h
delay). The source is short because the title would be cut to `Alarme ..`:

```yaml
# automation.alarme_hp_dimplex  (top of actions, before the 16h delay)
- event: busybar_notify
  event_data:
    kind: alarme_hp
    source: "PAC"
    title: "Alarme PAC"
    message: "Haute pression détectée"
```

BC-250 GPU temperature — the three automations already exist (80 / 85 / 90 °C, trigger
`sensor.bc_250_gpu_temperature`); add one block after the `script.canal` action in each of them.
The `°` is left out on purpose: `C` reads cleanly on the bar, and the source always fits.

```yaml
# automation.bc_250_80_degc_chaud  (after script.canal)
- event: busybar_notify
  event_data:
    kind: bc250
    source: "BC250 {{ states('sensor.bc_250_gpu_temperature') | int }}C"
    title: "BC-250 — chauffage"
    message: "GPU {{ states('sensor.bc_250_gpu_temperature') }} C"
```

```yaml
# automation.bc_250_85_degc_attention  (after script.canal)
- event: busybar_notify
  event_data:
    kind: bc250
    source: "BC250 {{ states('sensor.bc_250_gpu_temperature') | int }}C"
    title: "BC-250 — attention"
    message: "GPU {{ states('sensor.bc_250_gpu_temperature') }} C"
```

```yaml
# automation.bc_250_90_degc_critique  (after script.canal)
- event: busybar_notify
  event_data:
    kind: bc250
    source: "BC250 {{ states('sensor.bc_250_gpu_temperature') | int }}C"
    title: "BC-250 — critique"
    message: "GPU {{ states('sensor.bc_250_gpu_temperature') }} C"
```

`kind` is matched case- and space-insensitively (`_` and `-` count as spaces), and one leading
article is dropped, so `un chat`, `une personne`, `des colis`, `le livreur` and `l'oiseau` all land
on the right picture:

| `kind` in the event | picture |
| --- | --- |
| `une personne`, `plusieurs personnes`, `personne` | a person |
| `livreur`, `livraison` | a courier with a parcel |
| `colis`, `paquet` | a parcel |
| `chat`, `chien`, `renard`, `oiseau`, `biche` | an animal face |
| `vehicule`, `voiture`, `camion` | a van |
| `alarme_hp`, `pac` | a blinking fan |
| `bc250`, `bc 250`, `gpu`, `gpu temp`, `gpu temperature`, `temperature`, `temp`, `chaud`, `surchauffe` | a thermometer (GPU temperature) |
| anything else | a bell |

A kind that only *starts* with one of those names still matches on its longest leading run of
words, so a whole title can be sent as the kind: `kind_for("BC-250 90°C")` is the thermometer too.

## Regenerating the pictures

The app writes them at startup, but they can be written by hand (and inspected) without the bar:

```
python notifyanim.py --out cache --theme day     # or --theme night
```

`cache/` is git-ignored: the files are generated, and one set per theme keeps the colours baked in.
