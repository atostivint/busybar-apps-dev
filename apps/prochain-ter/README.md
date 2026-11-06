# Prochain TER

Next TER from your home station to Rennes (morning) and back (evening) on the BUSY Bar, with the
time you must start the car, delays/cancellations, and a four-note chiptune chime.

- Data, no token: BreizhGo static GTFS + SNCF GTFS-RT trip updates (transport.data.gouv.fr).
  Static and real-time trip ids differ: matched on (train number, service date), stops on UIC code.
- For the train you will take (D = its departure, delay included): `go` = D - (drive + parking),
  `prepare` = go - `--prep-min`; `--slack-min` (default 3) is the margin after `go`.
  Every screen is the same layout: TER logo on a block whose colour says what is going on
  (plain = fine, yellow = prepare/delay, green = go, red = cancelled/too late), two small lines beside it
  (long text scrolls on the bar itself), and a bar that drains along the bottom for countdowns.
  The logo + train number shows once when a train comes up, then the rotation:
  1. countdown (9 s): before prepare `06:58 / PARTIR A 06:49`; prepare (yellow) a scrolling
     `PREPARE-TOI POUR PARTIR A 06:49` with the minutes left in the block instead of the logo; go (green)
     `PARTEZ` with the seconds left before it gets too tight (`95 SEC`) in the block, red bar. At go this screen stays alone, with a chime.
  2. clock (4 s)  3. departure time + `A TEMPS` / `+4 MIN` (4 s)
  Too late for a train: `07:40 / PROCHAIN TER - PARTIR A 07:31` (scrolling).
  A cancelled train shows first: red logo block, `06:58 / ANNULE`. In the evening there is no prepare step.
- The screen stays blank (the bar keeps its other apps) until a train is about to matter: `--show-ahead`
  minutes (default 15) before you must start preparing, while a train is too late to catch but has not
  left, and for 2 minutes after the last train. Set the manager variation priority above your other apps (85).
- Snooze: the bar's START button (`--snooze-button start|ok|back|off`) dismisses the train on screen and
  stops the sound; alerts for it stop too. Button presses are read from the bar's state stream (`buttons.py`).
- Themes: day = white on blue, `--night` = amber on black (dimmest).
- Windows: `--morning 06:00-09:00` (station -> Rennes), `--evening 16:30-19:30` (Rennes -> station),
  `--days mon,...`. Outside them the app draws nothing and does not poll. `--demo` ignores them.
- Leave-by = drive + `--parking-min` + `--prep-min`. Drive times come from
  `python tools/prochain_drive_times.py "<address>"` (Nominatim + OSRM) into `drive_times.json`
  (git-ignored); `--drive-min` overrides.
- Chime: synthesised C-G (long) A-E (short), `--chime-volume` 0-100 (chime only, not the bar's master
  volume). Put your own `chime.snd` next to `app.py` to replace it. Plays at 15/5/0 min before leave-by,
  on a delay change >= 3 min, and on cancellation.
- Engine: when it is time to go, a synthesised starter + idle rumble plays instead of the chime
  (`--no-engine` to turn off, own `engine.snd` to replace; same `--chime-volume`).
- Traffic: with a free TomTom key (`TOMTOM_KEY` env var or a `tomtom.key` file next to `app.py`, git-ignored)
  and `--work-address`, the car screen shown when no train is left reads `VOITURE / 52 MIN` (yellow when
  jams add 5+ min). Cached 5 min; free tier is 2500 requests/day.
- `--platform-home` / `--platform-rennes`: platform numbers, blank hides the block.
- `--simulate`: plays a fake story on a 15x clock (cancelled train, a train you must catch, a delay,
  every chime, the missed screen) in about 2.5 minutes; see `sim.py`. `--sim-speed` changes the speed.
- Tests: `python -m unittest test_core test_board` from this folder.

## Home Assistant as the data source

With `HA_URL` and `HA_TOKEN` both set, the app reads the train from Home Assistant instead of
recomputing it from GTFS / GTFS-RT. Otherwise (or when HA is down) it uses the GTFS path above, unchanged.

- Env vars: `HA_URL` (e.g. `http://homeassistant.local:8123`) and `HA_TOKEN` (a long-lived access token).
  `--ha-url` / `--ha-token` override them; prefer the variables, flags show in the process list.
  Nothing is stored in a file. Polled every 15 s, 5 s timeout, one retry on a network error.
- Entities read (`GET /api/states/<id>`):

  | entity | what the app uses |
  |---|---|
  | `sensor.ter_prochain_train` | state = minutes to departure or `off`; attributes `train`, `trip_id` |
  | `sensor.ter_phase` | `wait`, `annonce`, `prepare`, `go`, `late`, `off` |
  | `sensor.ter_heure_de_depart` | timestamp of the departure (delay already included) |
  | `sensor.ter_heure_de_depart_de_la_maison` | timestamp you leave home; attributes `drive_minutes`, `station_minutes`, `walk_minutes`, `total_minutes` |
  | `sensor.ter_heure_de_preparation` | timestamp you start getting ready |

- Mapping: the departure becomes the usual one-train list, with prepare-to-leave and leave-to-departure
  durations taken from the timestamps (`--prep-min`, `--drive-min`, `--parking-min` are ignored).
  `annonce` shows as `wait`, `prepare` as `prep`. The screens still step through phases from those
  timestamps every second, so the phase on the bar can differ from `sensor.ter_phase` by the `--slack-min` margin.
- Fallback: HA unreachable, token rejected (401) or an unexpected payload -> that cycle uses GTFS and a
  line is logged once. `off` is not a failure: it means no train, and the bar stays blank.
  HA carries no cancellation flag, so the red cancelled screen only exists on the GTFS path.
- Direction from location (`sensor.ter_lieu`; state `maison`, `bureau`, `gare_rennes`, `gare_caulnes`,
  `ailleurs`, `zone`, `inconnu`; attributes `age_minutes`, `stale`, `source_state`, `activity`):
  `bureau` / `gare_rennes` = return trip (Rennes -> station), `maison` / `gare_caulnes` = outbound, but only
  when `stale` is explicitly false. Anything else (other places, stale, missing entity) leaves the
  `--morning` / `--evening` clock windows in charge, exactly as without HA. A trusted location also keeps the
  app active outside those windows (return trip at the office at 21:00, outbound at home at 11:00); the log
  says so once ("location keeps the app awake ...") and once more when it stops. Outside the windows the
  board comes from GTFS, since HA's sensor serves no window then. `--demo` / `--simulate` ignore all this.
  `sensor.ter_prochain_train` follows HA's own clock window, so when the location disagrees with the window
  (15:00 and you are at the office) that direction's board comes from GTFS; HA stays the source when they agree.
- Check it from this folder: `HA_URL=... HA_TOKEN=... python ha.py` prints the parsed state.

```
export HA_URL=http://homeassistant.local:8123
export HA_TOKEN=...            # never commit it
python app.py --demo           # log: "data source: Home Assistant"
```

Not done: Rennes bus/metro leg, replacement buses, Navitia as an extra source.
