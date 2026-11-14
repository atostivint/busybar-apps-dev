"""Alert screens for the 72x16 front display, as BUSY Bar draw elements.

One layout: a 26x16 colour block on the left, holding the kind's looping animation (or a static
"!" when the upload failed), then where the event was detected (source) on one line and the time
under it, in the readable small font. Nothing scrolls and there is no message line: the picture
says what happened, the text only says where and when.

Two themes, in the spirit of prochain-ter: "day" (white on near-black, amber block) and "night"
(amber on black; the black background draws no pixels, so it is the dimmest option).

Every screen returns the full element list (CLAUDE.md gotcha 4: always redraw everything), and
every string goes through ascii_fold(): the bar fonts have no accents.
"""

THEMES = {
    "day": dict(bg="#181818FF", fg="#FFFFFFFF", sub="#B0B0B0FF", warn="#FFD400FF", bad="#FF3B30FF",
                block="#FFAA00FF", on_block="#181818FF"),
    "night": dict(bg=None, fg="#FFA500FF", sub="#C0C0C0FF", warn="#FF3B30FF", bad="#FF3B30FF",
                  block="#FFA500FF", on_block="#000000FF"),
}

LED_ALERT = "#FFAA00FF"  # the orange notification LED, the colour of the block

RX = 27  # the text area beside the block: x 27..71
LABEL_Y, CLOCK_Y = -1, 6  # the two small-font rows: the label on top, the clock on the next one
LABEL_ROOM = 44  # px of text area a label may use (x 27..71)
CHAR_W = 4.5  # conservative advance of one small character: 44 / 4.5 = 9 characters fit
NOW_X = 71  # the clock is right aligned here
LEVELS = 6  # edge-shading steps between the block colour and the ink (notifyanim.py uses this)


# Accented and typographic characters Home Assistant sends, folded to ASCII. Anything that is
# still not printable ASCII (emoji, CJK, control characters) is dropped: the bar could not show it.
FOLD = {
    "à": "a", "á": "a", "â": "a", "ä": "a", "ã": "a", "å": "a", "ā": "a",
    "ç": "c", "ć": "c", "č": "c",
    "è": "e", "é": "e", "ê": "e", "ë": "e", "ē": "e", "ę": "e",
    "ì": "i", "í": "i", "î": "i", "ï": "i", "ī": "i",
    "ñ": "n", "ń": "n",
    "ò": "o", "ó": "o", "ô": "o", "ö": "o", "õ": "o", "ø": "o", "ō": "o",
    "ù": "u", "ú": "u", "û": "u", "ü": "u", "ū": "u",
    "ý": "y", "ÿ": "y",
    "š": "s", "ž": "z", "ł": "l", "đ": "d", "ß": "ss", "œ": "oe", "æ": "ae",
    "À": "A", "Á": "A", "Â": "A", "Ä": "A", "Ã": "A", "Å": "A",
    "Ç": "C", "Č": "C",
    "È": "E", "É": "E", "Ê": "E", "Ë": "E",
    "Ì": "I", "Í": "I", "Î": "I", "Ï": "I",
    "Ñ": "N",
    "Ò": "O", "Ó": "O", "Ô": "O", "Ö": "O", "Ø": "O",
    "Ù": "U", "Ú": "U", "Û": "U", "Ü": "U",
    "Ý": "Y", "Œ": "OE", "Æ": "AE",
    "’": "'", "‘": "'", "‚": "'", "“": '"', "”": '"', "«": '"', "»": '"',
    "–": "-", "—": "-", "‒": "-", "−": "-", "·": "-", "•": "-",
    "…": "...", "°": "o", "²": "2", "³": "3", "µ": "u", "€": "EUR", "£": "GBP",
}


def ascii_fold(s):
    """Accents and typographic punctuation to ASCII, everything unprintable dropped.

    The bar fonts only have ASCII, and a stray non-ASCII byte makes the firmware draw nothing at
    all for the line, so this runs on the title, the message and the time.
    """
    out = []
    for ch in str(s):
        folded = FOLD.get(ch)
        if folded is not None:
            out.append(folded)
        elif " " <= ch <= "~":  # printable ASCII, space included
            out.append(ch)
        elif ch in "\t\n\r":
            out.append(" ")
        # anything else (emoji, CJK, control characters) is dropped
    return "".join(out)


def _mix(a, b, k):
    """Blend '#RRGGBBAA' a towards b by k/LEVELS -> '#RRGGBB'."""
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * k / LEVELS):02X}" for x, y in zip(ca, cb))


def _rect(i, x, y, w, h, col):
    return {"id": i, "type": "rectangle", "x": x, "y": y, "width": w, "height": h,
            "fill": "solid", "fill_colors": [col], "border_width": 0}


def _bitmap(i, rows, pal, x=0, y=0):
    """xpmbitmap from a list of equal-length strings; pal maps a character to a '#RRGGBB' colour."""
    colors = [". c none"] + [f"{ch} c {col}" for ch, col in pal.items()]
    head = f"! XPM2\n{len(rows[0])} {len(rows)} {len(pal) + 1} 1\n" + "\n".join(colors) + "\n"
    data = head + "\n".join(rows) + "\n"
    return {"id": i, "type": "xpmbitmap", "x": x, "y": y, "width": len(rows[0]), "height": len(rows), "data": data}


def _text(i, s, x, y, col, font="small", align="top_left"):
    """One line, no scrolling: the alert screen only carries a short label and the clock."""
    return {"id": i, "type": "text", "text": s, "font": font, "x": x, "y": y,
            "align": align, "color": col}


def _base(th):
    return [_rect("bg", 0, 0, 72, 16, th["bg"])] if th["bg"] else []


def _fit(text, room=LABEL_ROOM, char=CHAR_W):
    """Cut a label down to the text area, keeping two cells for the "..".

    4.5 px a character is conservative for the small font, so a line this accepts stays between
    x=27 and x=71 instead of running off the screen.
    """
    limit = max(3, int(room / char))
    if len(text) <= limit:
        return text
    return text[:limit - 2].rstrip() + ".."


def _label(source, title):
    """The one line of text: where it was detected (source), else the title Home Assistant sent."""
    return _fit(ascii_fold(source or title))


# A static "!" for the block, drawn when this kind's animation was not uploaded (bar busy, asset
# locked): the screen still says something rather than showing an empty colour block.
BANG = [
    "..I..",
    "..I..",
    "..I..",
    "..I..",
    ".....",
    "..I..",
]


def _bang(i, on_block):
    return _bitmap(i, BANG, {"I": on_block[:7]}, (26 - len(BANG[0])) // 2, (16 - len(BANG)) // 2)


def alert(theme, kind, title, message, hhmm, anim_path, source=""):
    """The notification screen: the picture in the block, where it was detected, and the time.

    Two lines in the readable small font, neither scrolling: the picture already says what the
    event is (a person, a parcel, a hot GPU), so the text only has to say *where* — the camera or
    the place (source) — and *when*. `message` and `kind` are accepted for the caller and ignored.

    anim_path is the remote name of the uploaded .anim; None falls back to a static "!" in the block.
    """
    th = THEMES[theme]
    els = _base(th)
    if anim_path:
        els.append({"id": "anim", "type": "animation", "path": anim_path, "x": 0, "y": 0, "loop": True})
    else:
        els += [_rect("lb", 0, 0, 26, 16, th["block"]), _bang("bang", th["on_block"])]
    els.append(_text("a", _label(source, title), RX, LABEL_Y, th["fg"]))
    els.append(_text("now", ascii_fold(hhmm)[:5], NOW_X, CLOCK_Y, th["sub"], align="top_right"))
    return els
