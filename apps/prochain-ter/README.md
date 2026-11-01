# Prochain TER

Next TER from your home station to Rennes (morning) and back (evening) on the BUSY Bar, with the
time you must start the car, delays/cancellations, and a four-note chiptune chime.

- Data, no token: BreizhGo static GTFS + SNCF GTFS-RT trip updates (transport.data.gouv.fr).
  Static and real-time trip ids differ: matched on (train number, service date), stops on UIC code.
- Screens rotate: panel (platform, time, punctuality) / TER + train number / leave-by countdown.
  Cancelled train shows first, then the next catchable one. Under 1 min to leave: `PARTEZ !`.
- Themes: day = white on blue, `--night` = amber on black (dimmest).
- Windows: `--morning 06:00-09:00` (station -> Rennes), `--evening 16:30-19:30` (Rennes -> station),
  `--days mon,...`. Outside them the app draws nothing and does not poll. `--demo` ignores them.
- Leave-by = drive + `--parking-min` + `--prep-min`. Drive times come from
  `python tools/prochain_drive_times.py "<address>"` (Nominatim + OSRM) into `drive_times.json`
  (git-ignored); `--drive-min` overrides.
- Chime: synthesised C-G (long) A-E (short), `--chime-volume` 0-100 (chime only, not the bar's master
  volume). Put your own `chime.snd` next to `app.py` to replace it. Plays at 15/5/0 min before leave-by,
  on a delay change >= 3 min, and on cancellation.
- `--platform-home` / `--platform-rennes`: platform numbers, blank hides the block.
- Tests: `python -m unittest test_core test_board` from this folder.

Not done: Rennes bus/metro leg, replacement buses, Navitia as an extra source.
