"""The classic 80x15 web buttons, as BUSY Bar draw elements.

Each badge is a PNG/GIF from assets/buttons/. It is fitted to the 72x16 front display at 72x15,
flattened on black and emitted as one bitmap. A badge wider than the 72 px screen is still cut in
pieces at load time, because a bitmap may not be wider than the display; at 72 px there is only one.

An 80 px badge does not fit the 72 px screen, and resampling turns 1 px glyph strokes into grey
smudges. So the width is reduced by *deleting columns*, not by scaling: the 8 columns with the least
horizontal contrast (flat background, padding, the gaps between letters) are dropped, and every
remaining pixel is an original pixel. The glyphs stay sharp, the frame stays, and a 5 px button text
reads exactly as it was drawn. Rows are never scaled either: 15 of the 16 rows are used as they are.
"""
from pathlib import Path

from PIL import Image

BW, BH = 80, 15          # the standard "steal these buttons" chiclet
TARGET = (72, 15)        # width is all the screen has; 15 rows keep the aspect and the crisp text
LEFT = 72                # widest bitmap the front screen accepts
CHARS = "#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOP"


def _flatten(im):
    """RGBA on black, as the LED matrix composites it."""
    flat = Image.new("RGB", im.size, (0, 0, 0))
    flat.paste(im, mask=im.getchannel("A"))
    return flat


def _quantize(flat, colors=32):
    """At most `colors` colours, no dithering: dithering turns to visible noise on the LEDs."""
    return flat.quantize(colors=colors, method=Image.MEDIANCUT, dither=Image.NONE).convert("RGB")


def _reduce(flat):
    """The badge's own colours when it has <= 32 (the firmware limit); otherwise a 32-colour palette."""
    colors = flat.getcolors(1 << 20) or []
    return flat if len(colors) <= 32 else _quantize(flat, 32)


def _dist(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])


def _drop_columns(im, width):
    """Remove `im.width - width` columns, the ones with the least horizontal contrast (no resampling).

    A column's score sums the colour difference to its left and right neighbours over every row: a
    flat background, a margin or the gap between two letters scores ~0 and can go without touching a
    stroke, while an edge column scores high. The first and last columns are kept (the button frame).
    """
    px, w, h = im.load(), im.width, im.height
    need = w - width
    if need <= 0:
        return im
    score = []
    for x in range(w):
        e = 0
        for y in range(h):
            c = px[x, y]
            if x:
                e += _dist(c, px[x - 1, y])
            if x < w - 1:
                e += _dist(c, px[x + 1, y])
        score.append(e + (10 ** 9 if x in (0, w - 1) else 0))
    drop = set(sorted(range(w), key=lambda x: score[x])[:need])
    out = Image.new("RGB", (width, h))
    o, nx = out.load(), 0
    for x in range(w):
        if x in drop:
            continue
        for y in range(h):
            o[nx, y] = px[x, y]
        nx += 1
    return out


def _accent(flat):
    """The badge's signature colour: the most common clearly-saturated, reasonably bright colour."""
    best, score = (255, 255, 255), 0.0
    for count, rgb in flat.getcolors(flat.width * flat.height) or []:
        r, g, b = rgb
        hi, lo = max(rgb), min(rgb)
        if hi < 40 or hi - lo < 30:      # too dark or grey to read as a colour
            continue
        s = (hi - lo) / hi * (hi / 255)
        if count * s > score:
            best, score = rgb, count * s
    return best


def _xpm(rows, palette):
    """XPM2 with one character per colour, rows as strings over `palette` (char -> '#RRGGBB')."""
    chars = list(palette)
    head = f"! XPM2\n{len(rows[0])} {len(rows)} {len(chars)} 1\n"
    head += "".join(f"{c} c #{palette[c][0]:02X}{palette[c][1]:02X}{palette[c][2]:02X}\n" for c in chars)
    return head + "\n".join("".join(row) for row in rows)


class Badge:
    def __init__(self, path, size=TARGET):
        im = Image.open(path)
        im.load()
        im = im.convert("RGBA")
        self.name = Path(path).stem
        self.w, self.h = max(1, size[0]), max(1, size[1])
        base = _reduce(_flatten(im))
        if base.width > self.w:
            base = _drop_columns(base, self.w)
        if base.height != self.h:
            base = base.resize((base.width, self.h), Image.LANCZOS)
        self.flat = base
        self.accent = _accent(self.flat)
        q = self.flat
        colors = sorted(q.getcolors(self.w * self.h), reverse=True)
        palette = {CHARS[i]: rgb for i, (_, rgb) in enumerate(colors)}
        rev = {rgb: ch for ch, rgb in palette.items()}
        grid = [[rev[q.getpixel((x, y))] for x in range(self.w)] for y in range(self.h)]
        self.left = _xpm([row[:LEFT] for row in grid], palette)
        self.right = _xpm([row[LEFT:] for row in grid], palette) if self.w > LEFT else None
        self.quant = q

    def elements(self, i, x, y=0, prefix=""):
        """The draw elements for this badge at screen x (one element at the normal 72 px size)."""
        span = min(LEFT, self.w)
        els = [{"id": f"{prefix}b{i}l", "type": "xpmbitmap", "x": x, "y": y,
                "width": span, "height": self.h, "data": self.left}]
        if self.right:
            els.append({"id": f"{prefix}b{i}r", "type": "xpmbitmap", "x": x + LEFT, "y": y,
                        "width": self.w - LEFT, "height": self.h, "data": self.right})
        return els


def _frames(path):
    """How many frames an image has; 1 for stills and for anything Pillow cannot read."""
    try:
        with Image.open(path) as im:
            return getattr(im, "n_frames", 1)
    except Exception:
        return 1


def load(folder, limit=0, size=TARGET, names=None):
    """Every usable badge in `folder`, one per button.

    The collection ships some buttons twice (`firefox.gif` and `firefox.png`): same button, another
    file type, so showing both just repeats it. One file per stem is kept, preferring an animated GIF
    (it still shows its first frame here, but it is the richer original), then a PNG, then anything
    else. Returned in filename order; the app shuffles the order itself. `names`, when given, limits
    the scan to those file names (the files a site check has just added).
    """
    by_stem = {}
    for f in sorted(Path(folder).iterdir()):
        if names is not None and f.name not in names:
            continue
        if f.suffix.lower() in (".gif", ".png", ".jpg", ".jpeg", ".bmp", ".webp"):
            by_stem.setdefault(f.stem, []).append(f)

    def rank(path):
        return (0 if _frames(path) > 1 else 2 if path.suffix.lower() == ".png" else 1, path.name)

    out = []
    for stem in sorted(by_stem):
        f = min(by_stem[stem], key=rank)
        try:
            out.append(Badge(f, size))
        except Exception as e:       # one broken file must not take the clock down
            print(f"skipping {f.name}: {e}")
        if limit and len(out) >= limit:
            break
    return out
