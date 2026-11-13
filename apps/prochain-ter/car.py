"""The car of the "no more train" screen, as a looping .anim: it drives.

The road dashes slide under it one pixel per frame and the body bobs on its suspension once per
loop, so at a glance the bar says "you have to take the car". The firmware plays the frames itself
(see anim.py), so the screen still costs one request per redraw instead of one per frame.

Colours are baked in (one file per theme) and the background is transparent, so the colour block
behind it shows through, exactly like the still bitmap it replaces.
"""
import math

import anim
import board

W, H = 26, 16  # the colour block: the car keeps to its window, like the still bitmap
FPS, FRAMES = 20, 24  # a 1.2 s loop: 24 px of road (4 dash periods) and one bob, so the wrap is invisible
CAR_X, CAR_Y = 1, 3  # where board.CAR sits on the block
ROAD_Y = (14, 15)  # the two rows under the wheels
DASH = 3  # lit pixels, then as many dark ones


def _rgb(color):
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def _put(px, x, y, rgb, alpha):
    i = (y * W + x) * 4
    px[i], px[i + 1], px[i + 2], px[i + 3] = rgb[0], rgb[1], rgb[2], alpha


def _coverage():
    """board.CAR edge coverage as a float grid, at its place on the block."""
    grid = [[0.0] * W for _ in range(H)]
    for r, row in enumerate(board.CAR):
        for c, ch in enumerate(row):
            grid[CAR_Y + r][CAR_X + c] = int(ch) / board.LEVELS
    return grid


def frames(block, on_block):
    """The frames, RGBA bytes each: pass them through anim.rgba_to_bgra() to anim.write_anim().
    block/on_block are the theme colours the still bitmap was shaded with."""
    car, ink, road = _coverage(), _rgb(on_block), _rgb(board._mix(block, on_block, 2))
    out = []
    for f in range(FRAMES):
        bob = 0.5 - 0.5 * math.cos(2 * math.pi * f / FRAMES)  # 0 -> 1 -> 0: one bump per loop
        alpha = [[0.0] * W for _ in range(H)]
        for y in range(H):
            for x in range(W):
                if car[y][x]:
                    alpha[y][x] += car[y][x] * (1 - bob)  # the bob splits a row over two rows
                    if y + 1 < H:
                        alpha[y + 1][x] += car[y][x] * bob
        px = bytearray(W * H * 4)
        for y in ROAD_Y:  # the road first: the car drives over it
            for x in range(W):
                if ((x + f) // DASH) % 2 == 0:
                    _put(px, x, y, road, 255)
        for y in range(H):
            for x in range(W):
                if alpha[y][x] > 0.004:
                    _put(px, x, y, ink, round(255 * min(1.0, alpha[y][x])))
        out.append(bytes(px))
    return out


def write(path, block, on_block):
    """Writes the .anim for those theme colours."""
    anim.write_anim(path, [anim.rgba_to_bgra(f) for f in frames(block, on_block)], W, H, FPS)
    return path
