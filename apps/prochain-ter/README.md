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

Not done: Rennes bus/metro leg, replacement buses, Navitia as an extra source.
