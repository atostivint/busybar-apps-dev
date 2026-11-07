"""Composition: the whole 72x15 button, with the time drawn straight on top of it.

The same functions build the draw elements for the bar and the preview image, so the preview is
faithful. A badge is 80x15 and the front display 72x16: the badge is fitted to 72x15 by dropping its
8 most redundant columns (see belt.py), so every pixel stays 1:1 and the text stays sharp.

The clock is not a plate: it is white 3x5 digits with a 1 px black outline, so it stays readable on
any button while only its own pixels cover the image. The outline is part of the same xpmbitmap, and
everything that is neither glyph nor outline is transparent, so the artwork shows through.

The chip walks the four corners, one per badge swap, so the same part of the artwork is not hidden
every time (`next_corner`). `--clock` picks the starting corner.
"""
import canvas

CARD_GAP = 1                    # between two glyphs of the clock
CORNERS = ("bottom-left", "bottom-right", "top-right", "top-left")   # clockwise
NEIGHBOURS = ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1))
XPM_CHARS = "abcdefghijklmnopqrstuvwxyz#$%&'()*+,-/0123456789:;<=>?@ABCDEFGHIJKLMNOPQ"


def clock_size(hhmm="00:00"):
    """(width, height) of the clock element: the text plus 1 px of outline on each side."""
    w = canvas.text_width(hhmm, 1, CARD_GAP)
    return w + 2, 5 + 2


def clock_at(corner, hhmm="00:00"):
    """(x, y) of the clock element: flush with the screen edges in the chosen corner."""
    w, h = clock_size(hhmm)
    x = 0 if "left" in corner else canvas.W - w
    y = 0 if "top" in corner else canvas.H - h
    return x, y


def next_corner(corner, step=1):
    """`corner` moved `step` places clockwise."""
    if corner not in CORNERS:
        return corner
    return CORNERS[(CORNERS.index(corner) + step) % len(CORNERS)]


def clock_cells(hhmm, corner="bottom-left"):
    """{(screen x, screen y): colour} for the digits and their outline; nothing else is painted."""
    x, y = clock_at(corner, hhmm)
    cells = {}
    cx = x + 1                                  # 1 px of outline on the left
    for ch in hhmm:
        g = canvas.GLYPHS.get(ch, canvas.GLYPHS[" "])
        for r, row in enumerate(g):
            for q, bit in enumerate(row):
                if bit == "1":
                    cells[(cx + q, y + 1 + r)] = (255, 255, 255)
        cx += len(g[0]) + CARD_GAP
    outline = {}
    lit = set(cells)
    for px, py in lit:                          # 8-neighbour outline, the glyph wins on overlap
        for dx, dy in NEIGHBOURS:
            p = (px + dx, py + dy)
            if p not in lit and 0 <= p[0] < canvas.W and 0 <= p[1] < canvas.H:
                outline[p] = (0, 0, 0)
    return {**outline, **cells}


def clock_element(hhmm, corner="bottom-left"):
    """The clock as one xpmbitmap element: white digits, black outline, transparent elsewhere."""
    w, h = clock_size(hhmm)
    x, y = clock_at(corner, hhmm)
    cells = clock_cells(hhmm, corner)
    lookup, order, rows = {}, [], []
    for yy in range(y, y + h):
        row = []
        for xx in range(x, x + w):
            rgb = cells.get((xx, yy))
            if rgb is None:
                row.append(".")
                continue
            if rgb not in lookup:
                lookup[rgb] = XPM_CHARS[len(order)]
                order.append(rgb)
            row.append(lookup[rgb])
        rows.append("".join(row))
    head = f"! XPM2\n{w} {h} {len(order) + 1} 1\n. c none\n"
    head += "".join(f"{lookup[rgb]} c #{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}\n" for rgb in order)
    return {"id": "clock", "type": "xpmbitmap", "x": x, "y": y, "width": w, "height": h,
            "data": head + "\n".join(rows) + "\n"}


def elements(badge, index, hhmm, corner="bottom-left"):
    """The draw list: the badge, then the clock on top."""
    els = badge.elements(0, 0, 0, "")
    els.append(clock_element(hhmm, corner))
    return els


def frame_canvas(badge, hhmm, corner="bottom-left"):
    """The whole 72x16 frame as a Canvas, for the preview."""
    c = canvas.Canvas()
    c.blit(badge.quant, 0, 0)
    for (x, y), rgb in clock_cells(hhmm, corner).items():
        c.px(x, y, rgb)
    return c
