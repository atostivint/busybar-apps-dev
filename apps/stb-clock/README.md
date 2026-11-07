# Steal These Buttons

One whole classic web button at a time on the BUSY Bar's front display, with the time drawn straight
on top of it. Every `--hold` seconds the button is swapped for the next one with a hard cut: no
sliding, no fading, no animation.

The buttons come from the [Steal These Buttons](https://taylor.fyi/buttons/) collection. 111 files sit
in `assets/buttons/`, but some buttons are there twice as `name.gif` and `name.png`; only one file per
button is kept (animated GIF > PNG > GIF), so the rotation is 85 different buttons, shuffled at every
start.

## The frame

- **The whole button, crisp.** The display is 72x16 and a button is 80x15. Instead of scaling the
  image (which smears 1 px glyph strokes into grey), the 8 columns with the least horizontal contrast
  are **deleted** - flat background, padding and the gaps between letters score ~0 - so every
  remaining pixel is an original pixel and the 5 px button text stays sharp. The frame columns are
  never dropped. Result: 72x15, all 15 rows, 72 of the 80 columns (nothing meaningful is lost).
- **The clock is drawn on the image, transparent**: only its own glyphs are painted, everything else
  is `none`, so the button shows through. The digit colour is black or white, whichever leaves the
  fewest glyph pixels under a readable contrast (`bad_fraction()`), so it is a per-button choice.
- **It goes where it can be read**: `--clock auto` (the default) rejects corners where more than 5 %
  of the digits would be hard to see, then takes the emptiest of the rest (edge energy: flat
  background ~0, text and logos high). A 15 % busyness nudge keeps it moving from button to button
  instead of parking on the same empty spot for 60 of the 85 buttons. `--clock bottom-left` (etc.)
  pins one corner.
- **Flush against the border**: `choose_align()` pushes the time outward so the digits touch the
  button's frame (the halo is clipped on that side). If that would put more than 5 % of the digits
  under a hard-to-read contrast, it backs off 1 px (the old default) or 2 px to line up with the
  button's inner white line - the clock only keeps its distance when the artwork demands it.
- **Hollow option**: `--clock-style outline` paints only the 1 px halo, so the button shows through
  the strokes. It only works with a **black** halo: a white halo on a light button disappears, so in
  that case the app falls back to normal filled digits. Filled is still the default.
- **Two small fallbacks, only when the art leaves no choice**: if a few digits are still hard to see
  (3 of 85 buttons) the clock gets a 1 px halo in the opposite colour; if the button is a busy photo
  where no corner is clear (1 of 85, The Beatles), it gets a small solid black plate. Everything else
  is painted on the artwork with no extra pixel.
- **The wheel switches pictures**: turn it forward or back to step through the buttons (or click it to
  go one forward); the automatic swap pauses for a full `--hold` after a manual pick. `--wheel off`
  ignores it, and the app runs unchanged without the state stream.
- **Draws are rare**: one when the button swaps, one at each minute boundary when the digits change.
  Nothing else. A draw on the bar costs ~40-110 ms of its web server, and frequent draws made the
  display glitch (dropped elements, 400 "elements number limit exceeded"), which is why there is no
  frame timer and no continuous redraw. The swap is a single hard cut, not a slide.

## Controls

The bar's wheel is read from its own state stream (`/api/status/ws`, see `controls.py`): turn it to
step through the buttons, click it to go one forward. `--no-wheel` ignores it.

## Options

| option | default | |
|---|---|---|
| `--hold` | 10 | seconds each button stays on screen (3-120) |
| `--clock` | `auto` | `auto` = the emptiest corner, or pin `bottom-left`, `bottom-right`, `top-right`, `top-left` |
| `--wheel` | `on` | turn the wheel (or click it) to change picture (`off` ignores it) |
| `--outline` | `off` | force the 1 px halo (it is added automatically when needed) |
| `--clock-color` | `auto` | digit colour: `auto` black/white, or `inverse` of the button under the digits |
| `--clock-style` | `filled` | `filled` digits, or `outline` (hollow: only the halo is painted, the artwork shows inside the strokes; black halo only - white falls back to filled) |
| `--shuffle` | `on` | shuffle the order at start (`off` keeps filename order) |
| `--start` | 0 | badge index to start on (with `--no-shuffle`) |
| `--priority` | 60 | display priority 1-100 (the manager's variation priority overrides it) |
| `--host` | `10.0.4.20` | bar address; the manager passes its own |

## How it is drawn

The badge is a single 72x15 `xpmbitmap` (`b0l`); `belt.py` keeps the split at 72 columns for badges
wider than the display, but at the 72 px target only one element is emitted.

The clock is a second, small `xpmbitmap` (`clock`, 19x7): the digits only, `none` everywhere else, so
the button shows through. `layout.clock_colours()` samples the button under the digits and returns one
colour (the inverse, or black/white); `--outline on` adds the halo. `layout.choose_corner()` picks the corner (readable first,
then emptiest), `layout.choose_align()` nudges the element flush against the border (or 1-2 px in when
needed), `layout.needs_outline()` / `layout.needs_plate()` decide the fallbacks, and
`layout.clock_at()` places the element.

Every draw sends the whole scene, button first and clock last, because the element order inside one
draw is the z-order and a single element sent on its own can land behind the others. The elements keep
the same ids across swaps, so a new button replaces the old one on the bar instead of stacking on top
of it: an element stays on screen until its id is overwritten or cleared.

At startup the app deletes its own elements (`DELETE /api/display/draw`): on Windows the manager
hard-kills apps, so nothing at shutdown ever runs. The manager starts the app with `--host` pointing
at its proxy.

`layout.py` builds the same composition for the bar and for the preview, so the preview is faithful:
the only difference is that the preview samples `Badge.quant` pixels into an image instead of sending
elements.

## Adding buttons

Drop images into `assets/buttons/` - any GIF/PNG, flat or animated (only the first frame is used).
Everything is fitted to 72x15 once at startup, so 80x15 files look best: only 8 redundant columns
are dropped and nothing is scaled.
`tools/fetch_buttons.py` downloads the curated wishlist from taylor.fyi/buttons: `--all` gets
everything on the page, `--list names.txt` gets your own list (names without extension). Restart the
app to pick up new files.

## Preview

```bash
python tools/preview.py                          # preview.png + preview.gif
python tools/preview.py --time 09:41 --start 20
python tools/preview.py --count 10 --scale 8 --outline on --clock-color auto
```

`preview.png` is the first button at 6x (one LED = one block). `preview.gif` shows `--count` buttons
(default 6) for one second each. Both use `layout.frame_canvas()`, so they match the bar pixel for
pixel. The preview needs Pillow (the app itself also needs it to load the button images at startup).
