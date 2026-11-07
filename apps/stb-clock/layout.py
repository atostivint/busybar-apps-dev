"""Composition: the whole 72x15 button, with the time drawn straight on top of it.

The same functions build the draw elements for the bar and the preview image, so the preview is
faithful. A badge is 80x15 and the front display 72x16: the badge is fitted to 72x15 by dropping its
8 most redundant columns (see belt.py), so every pixel stays 1:1 and the text stays sharp.

The clock is not a plate: only the glyphs are painted, everything else in its xpmbitmap is `none`, so
the artwork shows through. The digit colour is picked from the button itself: black when the area
under the time is light, white when it is dark, so no outline is needed to stay readable. `--clock-
outline` adds a 1 px black outline back for the badges where neither reads well.

The chip walks the four corners, one per badge swap, so the same part of the artwork is not hidden
every time (`next_corner`). `--clock` picks the starting corner.
"""
import canvas

CARD_GAP = 1                    # between two glyphs of the clock
CORNERS = ("bottom-left", "bottom-right", "top-right", "top-left")   # clockwise
MOVE_WITHIN = 1.15              # auto: accept a slightly busier corner to keep the clock moving
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


def busy_score(badge, corner, hhmm="00:00"):
    """How much artwork is inside the clock area: the sum of the edge energy under the 19x7 element.

    A flat background scores ~0, a border ~0, text and logos score high. The clock goes where this is
    lowest, so turning a button into a clock covers the emptiest part of it.
    """
    x, y = clock_at(corner, hhmm)
    w, h = clock_size(hhmm)
    px = badge.quant.load()
    e = 0
    for yy in range(y, min(y + h, badge.h)):
        for xx in range(x, min(x + w, canvas.W)):
            c = px[xx, yy]
            if xx + 1 < canvas.W:
                e += sum(abs(c[i] - px[xx + 1, yy][i]) for i in range(3))
            if yy + 1 < badge.h:
                e += sum(abs(c[i] - px[xx, yy + 1][i]) for i in range(3))
    return e


def choose_corner(badge, hhmm="00:00", previous=None):
    """The emptiest corner; when it is the one already used, a near-tie moves the clock instead.

    Without that nudge, 61 of the 85 buttons would keep the clock in the same corner: same button
    layout, same empty spot. Accepting a corner up to 15 % busier keeps it moving without burying the
    time in the logo.
    """
    scores = {c: busy_score(badge, c, hhmm) for c in CORNERS}
    order = sorted(CORNERS, key=lambda c: scores[c])
    if previous and order[0] == previous and scores[order[1]] <= scores[order[0]] * MOVE_WITHIN:
        return order[1]
    return order[0]


def _lum(rgb):
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]


def _inverse(bg):
    """The opposite of a background colour, snapped to black/white when the inverse is a muddy grey."""
    inv = (255 - bg[0], 255 - bg[1], 255 - bg[2])
    if abs(_lum(bg) - _lum(inv)) < 60:          # mid-grey: inverting it changes nothing readable
        return (0, 0, 0) if _lum(bg) > 128 else (255, 255, 255)
    return inv


def clock_colours(badge, hhmm, corner="bottom-left", mode="inverse"):
    """One colour for the whole clock: the inverse of the button under it, or black/white.

    One colour for all glyphs, not one per pixel: inverting each pixel separately turns the digits
    into camouflage as soon as the artwork under them is not flat.
    """
    total = [0, 0, 0]
    lum = []
    for (x, y) in clock_cells(hhmm, corner, None, False):
        if 0 <= x < canvas.W and 0 <= y < badge.h:
            bg = badge.quant.getpixel((x, y))
            for i in range(3):
                total[i] += bg[i]
            lum.append(_lum(bg))
    pixels = clock_cells(hhmm, corner, None, False)
    if not lum:
        return {p: (255, 255, 255) for p in pixels}
    if mode == "inverse":
        avg = tuple(round(c / len(lum)) for c in total)
        return {p: _inverse(avg) for p in pixels}
    # The median, not the average: one black letter crossing the area must not flip a light button to
    # white digits. Median luminance says what most of the covered pixels are.
    lum.sort()
    colour = (0, 0, 0) if lum[len(lum) // 2] > 128 else (255, 255, 255)
    return {p: colour for p in pixels}


def clock_cells(hhmm, corner="bottom-left", colour=(255, 255, 255), outline=False):
    """{(screen x, screen y): colour} for the digits (and outline); nothing else is painted.

    `colour=None` only marks the glyph pixels (the value is a placeholder): clock_colours() uses it to
    know which background pixels the time will cover.
    """
    x, y = clock_at(corner, hhmm)
    cells = {}
    cx = x + 1                                  # 1 px of outline on the left
    for ch in hhmm:
        g = canvas.GLYPHS.get(ch, canvas.GLYPHS[" "])
        for r, row in enumerate(g):
            for q, bit in enumerate(row):
                if bit == "1":
                    cells[(cx + q, y + 1 + r)] = colour
        cx += len(g[0]) + CARD_GAP
    if not outline:
        return cells
    ring = {}
    lit = set(cells)
    for px, py in lit:                          # 8-neighbour outline, the glyph wins on overlap
        for dx, dy in NEIGHBOURS:
            p = (px + dx, py + dy)
            if p not in lit and 0 <= p[0] < canvas.W and 0 <= p[1] < canvas.H:
                ring[p] = (0, 0, 0)
    return {**ring, **cells}


def clock_element(badge, hhmm, corner="bottom-left", mode="inverse", outline=False):
    """The clock as one xpmbitmap element: digits only, everything else transparent."""
    w, h = clock_size(hhmm)
    x, y = clock_at(corner, hhmm)
    glyphs = clock_colours(badge, hhmm, corner, mode)
    cells = {}
    if outline:
        for p, c in clock_cells(hhmm, corner, (0, 0, 0), True).items():
            if p not in glyphs:             # the black halo, the glyphs win on overlap
                cells[p] = c
    cells.update(glyphs)
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


def elements(badge, index, hhmm, corner="bottom-left", mode="inverse", outline=False):
    """The draw list: the badge, then the clock on top."""
    els = badge.elements(0, 0, 0, "")
    els.append(clock_element(badge, hhmm, corner, mode, outline))
    return els


def frame_canvas(badge, hhmm, corner="bottom-left", mode="inverse", outline=False):
    """The whole 72x16 frame as a Canvas, for the preview."""
    c = canvas.Canvas()
    c.blit(badge.quant, 0, 0)
    glyphs = clock_colours(badge, hhmm, corner, mode)
    cells = clock_cells(hhmm, corner, (0, 0, 0), outline) if outline else {}
    cells.update(glyphs)
    for (x, y), rgb in cells.items():
        c.px(x, y, rgb)
    return c
