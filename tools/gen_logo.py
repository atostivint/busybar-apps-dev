"""Generate the repository logo: the BUSY Bar itself, its 72x16 LED screen lit orange.

    python tools/gen_logo.py

Writes docs/logo.png (1024x1024, GitHub avatar / README icon) and docs/banner.png
(1600x420, README banner). Everything is drawn from the bar's real proportions
(white rounded body, black glass, two feet) and its LED pitch, so the logo stays
crisp at any size. Needs Pillow for the rendering only.
"""

import os
from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")

ORANGE = (255, 122, 0)
ORANGE_HOT = (255, 190, 110)
BODY_TOP = (252, 251, 249)
BODY_BOTTOM = (226, 224, 219)
GLASS = (6, 6, 8)
BG_TOP = (18, 18, 24)
BG_BOTTOM = (9, 9, 12)

# 3x5 pixel font, the same shape family as the bar's own digits.
FONT3x5 = {
    "B": ("110", "101", "110", "101", "110"),
    "U": ("101", "101", "101", "101", "111"),
    "S": ("111", "100", "111", "001", "111"),
    "Y": ("101", "101", "010", "010", "010"),
    " ": ("000", "000", "000", "000", "000"),
}


def _vgrad(w, h, top, bottom):
    strip = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        strip.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
    return strip.resize((w, h), Image.BILINEAR)


def _radial(box_w, box_h, peak):
    """White blob fading to black, used as an alpha mask."""
    g = Image.radial_gradient("L").resize((box_w, box_h), Image.BICUBIC)
    g = g.point(lambda v: round(peak * (1 - v / 255) ** 2))
    return g


def _glow(layer, mask, color, blur, strength):
    """Paste a blurred, colored copy of `mask` onto `layer` (additive-ish)."""
    soft = mask.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: min(255, round(v * strength)))
    tint = Image.new("RGBA", layer.size, color + (0,))
    tint.putalpha(soft)
    layer.alpha_composite(tint)


def draw_bar(canvas, cx, cy, width, ss):
    """Draw the bar centered on (cx, cy); width is the body width in canvas pixels."""
    w = width
    h = w * 0.36
    r = w * 0.067
    x0, y0 = cx - w / 2, cy - h / 2
    S = lambda v: round(v * ss)
    box = lambda l, t, rr, b: (S(l), S(t), S(rr), S(b))

    # feet, behind the body
    fw, fh = w * 0.125, w * 0.038
    for fx in (x0 + w * 0.115, x0 + w * 0.755):
        d = ImageDraw.Draw(canvas)
        d.rounded_rectangle(box(fx, y0 + h - fh * 0.45, fx + fw, y0 + h + fh * 0.55),
                            radius=S(fw * 0.18), fill=(214, 212, 207, 255))
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle(box(x0, y0, x0 + w, y0 + h), radius=S(r), fill=(232, 230, 226, 255))

    # body face: gradient clipped to the same rounded rect
    body_h = S(h)
    face = _vgrad(max(1, S(w)), max(1, body_h), BODY_TOP, BODY_BOTTOM).convert("RGBA")
    mask = Image.new("L", (S(w), body_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, S(w) - 1, body_h - 1), radius=S(r), fill=255)
    canvas.paste(face, (S(x0), S(y0)), mask)

    # glass
    gx, gy = x0 + w * 0.052, y0 + h * 0.145
    gw, gh = w * 0.896, h * 0.69
    gr = w * 0.045
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle(box(gx, gy, gx + gw, gy + gh), radius=S(gr), fill=GLASS + (255,))

    # unlit LED grid, barely there
    pitch = gw / 46
    dot = max(1, round(pitch * 0.16 * ss))
    lit = Image.new("L", canvas.size, 0)
    dl = ImageDraw.Draw(lit)
    cols = int((gw - pitch * 0.5) / pitch)
    rows = int((gh - pitch * 0.5) / pitch)
    ox = gx + (gw - (cols - 1) * pitch) / 2
    oy = gy + (gh - (rows - 1) * pitch) / 2
    for j in range(rows):
        for i in range(cols):
            px, py = S(ox + i * pitch), S(oy + j * pitch)
            dl.ellipse((px - dot, py - dot, px + dot, py + dot), fill=255)
    _glow(canvas, lit, (150, 150, 170), S(pitch * 0.10), 0.10)

    # "BUSY" in the LED font, centered
    text = "BUSY"
    glyphs = 3 * len(text) + (len(text) - 1)
    cell = min((gh * 0.74) / 5, (gw * 0.62) / glyphs)
    gap = cell * 0.22
    step = cell + gap
    tw = (len(text) * 3 + len(text) - 1) * step - gap
    th = 5 * step - gap
    tx = gx + (gw - tw) / 2
    ty = gy + (gh - th) / 2

    led = Image.new("L", canvas.size, 0)
    led_hot = Image.new("L", canvas.size, 0)
    dl = ImageDraw.Draw(led)
    dh = ImageDraw.Draw(led_hot)
    for k, ch in enumerate(text):
        pattern = FONT3x5[ch]
        for row, bits in enumerate(pattern):
            for col, bit in enumerate(bits):
                if bit != "1":
                    continue
                px = tx + k * 4 * step + col * step
                py = ty + row * step
                dl.rounded_rectangle((S(px), S(py), S(px + cell), S(py + cell)),
                                     radius=S(cell * 0.22), fill=255)
                inset = cell * 0.32
                dh.rounded_rectangle((S(px + inset), S(py + inset), S(px + cell - inset), S(py + cell - inset)),
                                     radius=S(cell * 0.10), fill=255)

    # glass reflection over everything, then the light
    ref = Image.new("L", canvas.size, 0)
    ImageDraw.Draw(ref).rounded_rectangle(box(gx, gy, gx + gw, gy + gh * 0.45),
                                          radius=S(gr), fill=26)
    glass_tint = Image.new("RGBA", canvas.size, (255, 255, 255, 0))
    glass_tint.putalpha(ref.filter(ImageFilter.GaussianBlur(S(gh * 0.12))))
    canvas.alpha_composite(glass_tint)

    _glow(canvas, led, ORANGE, S(cell * 1.5), 0.55)
    _glow(canvas, led, ORANGE, S(cell * 0.30), 0.9)
    orange_layer = Image.new("RGBA", canvas.size, ORANGE + (0,))
    orange_layer.putalpha(led)
    canvas.alpha_composite(orange_layer)
    hot_layer = Image.new("RGBA", canvas.size, ORANGE_HOT + (0,))
    hot_layer.putalpha(led_hot)
    canvas.alpha_composite(hot_layer)


def logo(size=1024, ss=3):
    W = size * ss
    canvas = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    canvas.alpha_composite(_vgrad(W, W, BG_TOP, BG_BOTTOM).convert("RGBA"))

    # warm halo behind the bar
    halo = Image.new("L", (W, W), 0)
    halo.paste(_radial(round(W * 0.85), round(W * 0.80), 90), (round(W * 0.075), round(W * 0.12)))
    _glow(canvas, halo, ORANGE, W * 0.03, 0.55)

    # soft contact shadow
    sh = Image.new("L", (W, W), 0)
    ImageDraw.Draw(sh).ellipse((W * 0.14, W * 0.66, W * 0.86, W * 0.80), fill=150)
    _glow(canvas, sh, (0, 0, 0), W * 0.03, 1.0)

    draw_bar(canvas, size / 2, size * 0.505, size * 0.80, ss)

    # rounded icon tile
    mask = Image.new("L", (W, W), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, W - 1, W - 1), radius=round(W * 0.17), fill=255)
    out = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    out.paste(canvas, (0, 0), mask)
    return out.resize((size, size), Image.LANCZOS)


def banner(w=1600, h=420, ss=2):
    W, H = w * ss, h * ss
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    canvas.alpha_composite(_vgrad(W, H, (16, 16, 21), (8, 8, 10)).convert("RGBA"))

    # faint LED field in the background
    field = Image.new("L", (W, H), 0)
    df = ImageDraw.Draw(field)
    pitch = 19 * ss
    rad = max(1, round(1.1 * ss))
    for y in range(round(pitch / 2), H, pitch):
        for x in range(round(pitch / 2), W, pitch):
            df.ellipse((x - rad, y - rad, x + rad, y + rad), fill=255)
    field = field.filter(ImageFilter.GaussianBlur(0.6 * ss))
    _glow(canvas, field, (120, 130, 170), 0.4 * ss, 0.13)

    halo = Image.new("L", (W, H), 0)
    halo.paste(_radial(round(W * 0.38), round(W * 0.38), 90), (round(W * 0.045), round(H * 0.12)))
    _glow(canvas, halo, ORANGE, 0.01 * W, 0.5)

    sh = Image.new("L", (W, H), 0)
    ImageDraw.Draw(sh).ellipse((W * 0.06, H * 0.78, W * 0.41, H * 0.90), fill=150)
    _glow(canvas, sh, (0, 0, 0), 0.012 * W, 1.0)

    draw_bar(canvas, w * 0.235, h * 0.50, w * 0.365, ss)

    # wordmark, drawn on its own layer then centered against the bar
    text = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bold = ImageFont.truetype("C:/Windows/Fonts/bahnschrift.ttf", round(84 * ss))
    small = ImageFont.truetype("C:/Windows/Fonts/CascadiaMono.ttf", round(25 * ss))
    d = ImageDraw.Draw(text)
    x = round(W * 0.475)
    y = round(H * 0.20)
    d.text((x, y), "busybar", font=bold, fill=(248, 247, 245, 255), anchor="lt")
    dx = x + round(d.textlength("busybar", font=bold))
    d.text((dx, y), "-apps-dev", font=bold, fill=(255, 122, 0, 255), anchor="lt")

    rule_y = y + round(78 * ss)
    d.rounded_rectangle((x, rule_y, x + 84 * ss, rule_y + 4 * ss), radius=2 * ss,
                        fill=(255, 122, 0, 255))
    d.text((x, rule_y + 34 * ss), "apps for the 72×16 LED bar", font=small,
           fill=(168, 168, 180, 255), anchor="lt")
    d.text((x, rule_y + 68 * ss), "Python · busybar-manager or standalone", font=small,
           fill=(112, 112, 126, 255), anchor="lt")

    box = text.getbbox()
    block = text.crop(box)
    canvas.alpha_composite(block, (x, round(H / 2 - block.height / 2)))

    return canvas.resize((w, h), Image.LANCZOS)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    logo().save(os.path.join(OUT, "logo.png"))
    banner().save(os.path.join(OUT, "banner.png"))
    print("wrote docs/logo.png and docs/banner.png")
