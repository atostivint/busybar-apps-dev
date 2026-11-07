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
- **The clock is drawn on the image**, without a plate: white 3x5 digits with a 1 px black outline.
  The outline is what keeps it readable over a white, black or busy button, and it only paints the
  glyphs and their neighbours, so the artwork shows through everywhere else.
- **The clock walks the corners**: on each badge swap it moves one corner clockwise
  (`bottom-left` -> `bottom-right` -> `top-right` -> `top-left`), so the same part of the artwork is
  not hidden every time. `--clock` picks the starting corner, `--no-clock-cycle` parks it.
- **Draws are rare**: one when the button swaps, one at each minute boundary when the digits change.
  Nothing else. A draw on the bar costs ~40-110 ms of its web server, and frequent draws made the
  display glitch (dropped elements, 400 "elements number limit exceeded"), which is why there is no
  frame timer and no continuous redraw. The swap is a single hard cut, not a slide.

## Options

| option | default | |
|---|---|---|
| `--hold` | 10 | seconds each button stays on screen (3-120) |
| `--clock` | `bottom-left` | corner the clock starts in (`bottom-left`, `bottom-right`, `top-right`, `top-left`) |
| `--clock-cycle` | on | move the clock one corner clockwise on every badge swap (`--no-clock-cycle` to park it) |
| `--shuffle` | on | shuffle the order at startup (`--no-shuffle` keeps filename order) |
| `--start` | 0 | badge index to start on (with `--no-shuffle`) |
| `--priority` | 60 | display priority 1-100 (the manager's variation priority overrides it) |
| `--host` | `10.0.4.20` | bar address; the manager passes its own |

## How it is drawn

The badge is a single 72x15 `xpmbitmap` (`b0l`); `belt.py` keeps the split at 72 columns for badges
wider than the display, but at the 72 px target only one element is emitted.

The clock is a second, small `xpmbitmap` (`clock`, 19x7): white digits, black outline, and `none`
everywhere else, so the button shows through the gaps. `layout.clock_at()` places it flush in one of
the four corners; the app advances the corner on every swap.

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
python tools/preview.py --count 10 --scale 8
```

`preview.png` is the first button at 6x (one LED = one block). `preview.gif` shows `--count` buttons
(default 6) for one second each. Both use `layout.frame_canvas()`, so they match the bar pixel for
pixel. The preview needs Pillow (the app itself also needs it to load the button images at startup).
