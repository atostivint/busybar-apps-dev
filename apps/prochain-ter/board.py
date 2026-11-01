"""Station-board screens for the 72x16 front display, as BUSY Bar draw elements.

Two themes: "day" (white on blue, like the newer station screens) and "night" (amber on black,
the classic LED panel; the black background draws no pixels, so it is the dimmest option).
Every screen returns the full element list (CLAUDE.md gotcha 4: always redraw everything).
ASCII only: the bar fonts have no accents.
"""

THEMES = {
    "day": dict(bg="#0A3D9CFF", fg="#FFFFFFFF", sub="#9FD0FFFF", warn="#FFD400FF", bad="#FF3B30FF",
                block="#FFFFFFFF", on_block="#0A3D9CFF", on_bad="#FFFFFFFF", prep="#FFD400FF", go="#33FF66FF", track="#2C62C8FF"),
    "night": dict(bg=None, fg="#FFA500FF", sub="#C0C0C0FF", warn="#FF3B30FF", bad="#FF3B30FF",
                  block="#FFA500FF", on_block="#000000FF", on_bad="#000000FF", prep="#FFFFFFFF", go="#33FF66FF", track="#303030FF"),
}


# The TER swoosh, rendered from the official vector logo at 26x13 with 6 levels of edge
# coverage (0 = empty, 6 = solid) and a gentle contrast curve: smooth curves, no ragged edge.
LOGO = [
    "00000005000000000000000000", "00000065000000000000000000",
    "00000460000000000000000000", "00000640023000000000000000",
    "00006666652000000000000000", "00366663000000000000000000",
    "56666600000120000000000000", "00366000056546100465000000",
    "00662000660046001666000000", "00660001620660006456400000",
    "00663002666300166016610000", "00666666666556650004664133",
    "00166652056665000000266630",
]
LEVELS = 6


def _mix(a, b, k):
    """Blend '#RRGGBBAA' a towards b by k/LEVELS -> '#RRGGBB'."""
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * k / LEVELS):02X}" for x, y in zip(ca, cb))


def _shaded(i, rows, x, y, bg, fg):
    """Bitmap whose digits 0..LEVELS are edge coverage; pixels blend from the block colour (bg) to fg."""
    colors = ["0 c none"] + [f"{k} c {_mix(bg, fg, k)}" for k in range(1, LEVELS + 1)]
    head = f"! XPM2\n{len(rows[0])} {len(rows)} {LEVELS + 1} 1\n" + "\n".join(colors) + "\n"
    data = head + "\n".join(rows) + "\n"
    return {"id": i, "type": "xpmbitmap", "x": x, "y": y, "width": len(rows[0]), "height": len(rows), "data": data}


def _logo(i, x, y, bg, fg):
    """The TER logo, edge pixels blended between the block colour (bg) and the logo colour (fg)."""
    return _shaded(i, LOGO, x, y, bg, fg)


def _rect(i, x, y, w, h, col):
    return {"id": i, "type": "rectangle", "x": x, "y": y, "width": w, "height": h,
            "fill": "solid", "fill_colors": [col], "border_width": 0}


RX, RW = 27, 45  # the text area beside the block: x, width (7 small characters)


def _text(i, s, x, y, col, font="small", marquee=False):
    el = {"id": i, "type": "text", "text": s, "font": font, "x": x, "y": y, "align": "top_left", "color": col}
    if marquee and len(s) * 6 - 1 > RW:  # the bar scrolls it itself (px per minute), like a station board
        el.update(width=RW, scroll_rate=1800, scroll_start_delay=1000, scroll_repeat_delay=2500)
    return el


def _base(th):
    return [_rect("bg", 0, 0, 72, 16, th["bg"])] if th["bg"] else []


def _badge(th, block, on_block, l1, l2, c1, c2, bar=None, left=None):
    """The one layout: TER logo on a colour block (the colour says what is going on) and two small
    lines beside it, long text scrolling. bar = (fraction, colour) adds a draining bar underneath."""
    els = _base(th) + [_rect("lb", 0, 0, 26, 16, block)] + (left if left else [_logo("logo", 0, 2, block, on_block)])
    els += [_text("a", l1, RX, -1, c1, marquee=True), _text("b", l2, RX, 6, c2, marquee=True)]
    if bar:
        frac, col = bar
        els.append(_rect("track", RX, 14, 44, 2, th["track"]))
        if frac > 0:
            els.append(_rect("fill", RX, 14, max(1, round(44 * frac)), 2, col))
    return els


def identity(theme, number, destination):
    """The TER logo, train number and destination (shown once when a train comes up)."""
    th = THEMES[theme]
    return _badge(th, th["block"], th["on_block"], str(number)[:6], destination[:7], th["fg"], th["sub"])


def info(theme, dep, delay_min=0, cancelled=False):
    """Departure time and punctuality. Block: plain = on time, yellow = delayed, red = cancelled."""
    th = THEMES[theme]
    if cancelled:
        return _badge(th, th["bad"], th["on_bad"], dep, "ANNULE", th["fg"], th["bad"])
    if delay_min > 0:
        return _badge(th, th["prep"], th["on_block"], dep, f"+{delay_min} MIN", th["fg"], th["warn"])
    return _badge(th, th["block"], th["on_block"], dep, "A TEMPS", th["fg"], th["sub"])


DIGITS = {
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
}
BIG = {  # 3x5 digits, drawn at 2x for one or two digits: chunky and readable from far away
    "0": ["111", "101", "101", "101", "111"], "1": ["010", "110", "010", "010", "111"],
    "2": ["111", "001", "111", "100", "111"], "3": ["111", "001", "111", "001", "111"],
    "4": ["101", "101", "111", "001", "001"], "5": ["111", "100", "111", "001", "111"],
    "6": ["111", "100", "111", "101", "111"], "7": ["111", "001", "001", "001", "001"],
    "8": ["111", "101", "111", "101", "111"], "9": ["111", "101", "111", "001", "111"],
}
# the ring around the block, clockwise from the top middle (72 pixels)
RING = ([(x, 1) for x in range(13, 25)] + [(24, y) for y in range(2, 14)] + [(x, 14) for x in range(24, 0, -1)]
        + [(1, y) for y in range(13, 1, -1)] + [(x, 1) for x in range(1, 13)])


def _bitmap(i, rows, pal, x=0, y=0):
    """xpmbitmap from a list of equal-length strings; pal maps a character to a '#RRGGBB' colour."""
    colors = [". c none"] + [f"{ch} c {col}" for ch, col in pal.items()]
    head = f"! XPM2\n{len(rows[0])} {len(rows)} {len(pal) + 1} 1\n" + "\n".join(colors) + "\n"
    data = head + "\n".join(rows) + "\n"
    return {"id": i, "type": "xpmbitmap", "x": x, "y": y, "width": len(rows[0]), "height": len(rows), "data": data}


def _timer(block, on_block, number, frac):
    """Timer in the block, in place of the logo: the number in clean 5x7 digits inside a ring that
    drains clockwise (frac 1 = full ring)."""
    grid = [["."] * 26 for _ in range(16)]
    lit = round(max(0.0, min(1.0, frac)) * len(RING))
    for n, (x, y) in enumerate(RING):
        grid[y][x] = "D" if n < lit else "T"
    if len(number) <= 2:  # big: 6x10 digits, 2 px apart
        w = 8 * len(number) - 2
        x0, y0 = (26 - w) // 2, 3
        for k, ch in enumerate(number):
            for r, row in enumerate(BIG[ch]):
                for c, v in enumerate(row):
                    if v == "1":
                        for dy in (0, 1):
                            for dx in (0, 1):
                                grid[y0 + r * 2 + dy][x0 + k * 8 + c * 2 + dx] = "D"
    else:  # three digits: 5x7
        w = 6 * len(number) - 1
        x0 = (26 - w) // 2
        for k, ch in enumerate(number):
            for r, row in enumerate(DIGITS[ch]):
                for c, v in enumerate(row):
                    if v == "1":
                        grid[4 + r][x0 + k * 6 + c] = "D"
    return [_bitmap("n", ["".join(r) for r in grid], {"D": on_block[:7], "T": _mix(block, on_block, 2)})]


def steps(theme, ph, left_s, frac, go_hhmm, dep_hhmm):
    """The countdown. The block colour says what to do; the ring and the bar drain.
    wait  plain, logo   06:58 / PARTIR A 06:49 (scrolling)   bar: time until you start getting ready
    prep  yellow, minutes in the ring   PREPARE-TOI POUR PARTIR A 06:49 (scrolling) / MIN
    go    green, seconds in the ring    PARTEZ / SEC   red bar: slack left before it is too late
    The prep ring only moves once a minute: a redraw restarts the scrolling text.
    """
    th = THEMES[theme]
    if ph == "go":
        return _badge(th, th["go"], th["on_block"], "PARTEZ", "SEC", th["go"], th["sub"], (frac, th["bad"]),
                      left=_timer(th["go"], th["on_block"], str(max(0, int(left_s))), frac))
    if ph == "prep":
        mins = max(1, -(-int(left_s) // 60))
        total = max(mins, round(left_s / max(frac, 1e-6) / 60))
        return _badge(th, th["prep"], th["on_block"], f"PREPARE-TOI POUR PARTIR A {go_hhmm}", "MIN",
                      th["prep"], th["sub"], (mins / total, th["prep"]),
                      left=_timer(th["prep"], th["on_block"], str(mins), mins / total))
    return _badge(th, th["block"], th["on_block"], dep_hhmm, f"PARTIR A {go_hhmm}", th["fg"], th["sub"],
                  (frac, th["sub"]))


# Ford Mondeo estate, side view: traced from a hand-made outline (long roof, upright tailgate),
# rendered at 24x11 (height exaggerated a little, like pixel-art cars) with the logo's edge shading.
CAR = [
    "002344444444444200000000", "066621100600000363000000", "066300000500000005200000",
    "066300000500000000610000", "166666666666666666666410", "266645466666666666454663",
    "366566656666666665666565", "054666645555555546666452", "000666600000000006666000",
    "000366600000000003666000", "000024000000000000240000",
]


def next_train(theme, next_dep=None, next_go=None, drive=None):
    """Too late for this train (or nothing left): which train to take next, and when to leave for it.
    With nothing left it shows the car; `drive` ({"minutes", "delay_min"}) adds the live drive time."""
    th = THEMES[theme]
    if next_dep:
        return _badge(th, th["block"], th["on_block"], next_dep, f"PROCHAIN TER - PARTIR A {next_go}", th["fg"], th["sub"])
    car = _shaded("car", CAR, 1, 3, th["block"], th["on_block"])
    if drive:
        jam = drive["delay_min"] >= 5
        return _badge(th, th["block"], th["on_block"], "VOITURE", f"{drive['minutes']} MIN", th["fg"],
                      th["warn"] if jam else th["sub"], left=[car])
    return _badge(th, th["block"], th["on_block"], "PLUS DE", "TRAIN", th["fg"], th["fg"], left=[car])


def clock(theme, hhmm, destination):
    """The current time (desk clock)."""
    th = THEMES[theme]
    return _badge(th, th["block"], th["on_block"], hhmm, destination[:7], th["fg"], th["sub"])


def message(theme, line1, line2, bad=False):
    th = THEMES[theme]
    return _base(th) + [_text("a", line1, 1, 0, th["bad"] if bad else th["fg"]), _text("b", line2, 1, 8, th["sub"])]
