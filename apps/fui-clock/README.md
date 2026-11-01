# FUI Clock

A clock for the BUSY Bar (72x16 LEDs) in 25 sci-fi HUD designs.

![FUI Clock tour](preview.gif)

## Switching designs

- **Turn the wheel:** previous / next design. The new design is drawn live while you turn, then handed over to the
  pre-rendered minute without a jump.
- **Click the wheel:** next accent colour (on the `alarm` design: next warning sign).
- **Dashboard / flags:** `--design NAME` (or `all` to cycle every `--rotate` minutes), `--accent`, `--alarm-colour`,
  `--alarm-shape` (`triangle`, `circle`, `octagon`, `diamond`, `bolt`), `--hour12`, `--zones`, `--no-wheel`.

Designs: seg, thin, matrix, perimeter, radar, binary, brackets, pulse, telemetry, glitch, holo, hexbg, bars3, arc,
odometer, tape, rain, target, alarm, monolith, warp, world, dateline, spectrum, circuit.

## How it works

The bar can't draw a clock, so each minute is rendered ahead on the computer as a 60 s `.anim`, uploaded, and started
on the minute: the seconds and the ambient motion are played by the bar's firmware and the app sends about one request
a minute. Wheel input comes from the bar's `/api/status/ws` stream. The app needs a draw priority above the built-in
clock (80 works).

Pure Python standard library. Previews without a bar: `python -m fui.gallery --out gallery.html`.
Regenerate the picture above (needs Pillow): `python -m fui.preview`.
