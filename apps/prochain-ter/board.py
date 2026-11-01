"""Station-board screens for the 72x16 front display, as BUSY Bar draw elements.

Two themes: "day" (white on blue, like the newer station screens) and "night" (amber on black,
the classic LED panel; the black background draws no pixels, so it is the dimmest option).
Every screen returns the full element list (CLAUDE.md gotcha 4: always redraw everything).
ASCII only: the bar fonts have no accents.
"""

THEMES = {
    "day": dict(bg="#0A3D9CFF", fg="#FFFFFFFF", sub="#9FD0FFFF", warn="#FFD400FF", bad="#FF3B30FF",
                block="#FFFFFFFF", on_block="#0A3D9CFF", on_bad="#FFFFFFFF"),
    "night": dict(bg=None, fg="#FFA500FF", sub="#C0C0C0FF", warn="#FF3B30FF", bad="#FF3B30FF",
                  block="#FFA500FF", on_block="#000000FF", on_bad="#000000FF"),
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


def _logo(i, x, y, bg, fg):
    """Logo bitmap; edge pixels are blended between the block colour (bg) and the logo colour (fg)."""
    colors = ["0 c none"] + [f"{k} c {_mix(bg, fg, k)}" for k in range(1, LEVELS + 1)]
    head = f"! XPM2\n{len(LOGO[0])} {len(LOGO)} {LEVELS + 1} 1\n" + "\n".join(colors) + "\n"
    data = head + "\n".join(LOGO) + "\n"
    return {"id": i, "type": "xpmbitmap", "x": x, "y": y, "width": len(LOGO[0]), "height": len(LOGO), "data": data}


def _rect(i, x, y, w, h, col):
    return {"id": i, "type": "rectangle", "x": x, "y": y, "width": w, "height": h,
            "fill": "solid", "fill_colors": [col], "border_width": 0}


def _text(i, s, x, y, col, font="small"):
    return {"id": i, "type": "text", "text": s, "font": font, "x": x, "y": y,
            "align": "top_left", "color": col}


def _base(th):
    return [_rect("bg", 0, 0, 72, 16, th["bg"])] if th["bg"] else []


def panel(theme, dep, platform="", delay_min=0, cancelled=False):
    """Departure time + destination code, platform block, punctuality line."""
    th = THEMES[theme]
    x0 = 12 if platform else 1
    if cancelled:
        block, on_block, status, scol = th["bad"], th["on_bad"], "SUPPRIME", None
    elif delay_min > 0:
        block, on_block, status, scol = th["warn"], th["on_block"], f"+{delay_min} MIN", th["warn"]
    else:
        block, on_block, status, scol = th["block"], th["on_block"], "A L'HEURE", th["sub"]
    els = _base(th)
    if platform:
        els += [_rect("pf", 0, 0, 10, 16, block), _text("pn", platform[:1], 2, 1, on_block, "large")]
    els.append(_text("t", dep, x0, 0, th["fg"]))
    if cancelled:  # white-on-red bar: readable on both themes, no strike through the time
        els += [_rect("bar", x0, 9, 72 - x0, 7, th["bad"]), _text("b", status, x0 + 1, 8, th["on_bad"])]
    else:
        els.append(_text("b", status, x0, 8, scol))
    return els


def identity(theme, number, destination):
    """TER logo block + train number + destination."""
    th = THEMES[theme]
    return _base(th) + [_rect("lb", 0, 0, 26, 16, th["block"]),
                        _logo("logo", 0, 2, th["block"], th["on_block"]),
                        _text("t", str(number)[:6], 29, 0, th["fg"]), _text("b", destination[:7], 29, 8, th["sub"])]


def leave(theme, minutes, hhmm):
    """Minutes until you must start the car, with the leave-by time. Under 1 minute: PARTEZ !"""
    th = THEMES[theme]
    if minutes <= 0:
        return _base(th) + [_rect("pf", 0, 0, 72, 16, th["bad"]), _text("t", "PARTEZ !", 6, 3, th["on_bad"], "normal")]
    soon = minutes <= 15
    block = th["warn"] if soon and theme == "day" else th["block"]
    num = str(min(minutes, 99))
    return _base(th) + [_rect("pf", 0, 0, 19, 16, block),
                        _text("n", num, 2 if len(num) > 1 else 6, 1, th["on_block"], "large"),
                        _text("t", "PARTIR", 22, 0, th["fg"]),
                        _text("b", f"A {hhmm}", 22, 8, th["warn"] if soon else th["sub"])]


def message(theme, line1, line2, bad=False):
    th = THEMES[theme]
    return _base(th) + [_text("a", line1, 1, 0, th["bad"] if bad else th["fg"]), _text("b", line2, 1, 8, th["sub"])]
