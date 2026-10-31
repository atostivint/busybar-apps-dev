#!/usr/bin/env python3
"""Jam Intro: demoscene show-off animations with a logo banner.

Cycles flashy 72x16 pixel effects (plasma, starfield, fire, sparkle) behind a
banner image, so the bar looks alive on a jam table.

    python3 app.py                        # BUSY Bar over USB (always 10.0.4.20)
    python3 app.py --host 127.0.0.1:8080  # emulator or a Wi-Fi bar
    python3 app.py --effect plasma --banner banner.png

The banner defaults to `banner.png` next to this file: any PNG up to 72x16,
alpha-blended over the effect (transparent pixels let the effect through), read
with the stdlib only — drop in another PNG to change it. `--text` adds an
optional centred line in the device's own font instead.

Each frame is rendered to one 72x16 image and pushed as a single image element,
next to a static text element when --text is used. Pushing individual rectangles
costs ~3.6 ms each on the device, so a rect-per-pixel frame cannot beat 3-6 fps;
a full-frame image is a flat ~50 ms whatever it contains, so every effect here
stays smooth.
"""
import argparse
import base64
import http.client
import json
import math
import os
import random
import socket
import struct
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

APP = "jam-intro"
W, H = 72, 16

# ---------------------------------------------------------------------------
# BUSY Bar HTTP API — self-contained, stdlib only.
# Over USB the bar is always at 10.0.4.20; --host targets a Wi-Fi bar or the
# emulator. The device serves its own reference at http://10.0.4.20/docs
# ---------------------------------------------------------------------------


def endpoint(host, path=""):
    return "http://" + host.replace("http://", "").rstrip("/") + path


def post(base, path, data, content_type, token=None, timeout=5):
    headers = {"Content-Type": content_type}
    if token:
        headers["X-API-Token"] = token
    request = urllib.request.Request(base + path, data=data, method="POST", headers=headers)
    with urllib.request.urlopen(request, timeout=timeout):
        pass


def _png(pixels):
    """72x16 flat list of (r, g, b) -> minimal RGBA PNG bytes."""
    raw = bytearray()
    for y in range(H):
        raw.append(0)
        row = y * W
        for x in range(W):
            r, g, b = pixels[row + x]
            raw += bytes((r, g, b, 255))

    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 1))
            + chunk(b"IEND", b""))


def read_png(path):
    """Read a small non-interlaced 8-bit PNG (RGB or RGBA) into RGBA rows.

    Deliberately narrow: a banner is a handful of pixels, and staying stdlib-only
    keeps the app a single file with nothing to install.
    """
    blob = open(path, "rb").read()
    if blob[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG file")
    pos, idat, header = 8, bytearray(), None
    while pos + 8 <= len(blob):
        length, tag = struct.unpack(">I4s", blob[pos:pos + 8])
        data = blob[pos + 8:pos + 8 + length]
        if tag == b"IHDR":
            header = struct.unpack(">IIBBBBB", data)
        elif tag == b"IDAT":
            idat += data
        elif tag == b"IEND":
            break
        pos += 12 + length
    if header is None:
        raise ValueError("missing IHDR")
    width, height, depth, color_type, compression, filter_method, interlace = header
    if depth != 8 or compression != 0 or filter_method != 0 or interlace != 0:
        raise ValueError("only 8-bit non-interlaced PNGs are supported")
    if color_type not in (2, 6):
        raise ValueError("only RGB and RGBA PNGs are supported")
    channels = 3 if color_type == 2 else 4
    stride = width * channels
    raw = zlib.decompress(bytes(idat))

    rows, previous = [], bytearray(stride)
    offset = 0
    for _ in range(height):
        filter_type = raw[offset]
        line = bytearray(raw[offset + 1:offset + 1 + stride])
        offset += 1 + stride
        for i in range(stride):
            left = line[i - channels] if i >= channels else 0
            up = previous[i]
            up_left = previous[i - channels] if i >= channels else 0
            if filter_type == 1:
                line[i] = (line[i] + left) & 0xFF
            elif filter_type == 2:
                line[i] = (line[i] + up) & 0xFF
            elif filter_type == 3:
                line[i] = (line[i] + ((left + up) >> 1)) & 0xFF
            elif filter_type == 4:
                p = left + up - up_left
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - up_left)
                best = left if (pa <= pb and pa <= pc) else (up if pb <= pc else up_left)
                line[i] = (line[i] + best) & 0xFF
            elif filter_type != 0:
                raise ValueError("unknown PNG filter %d" % filter_type)
        rows.append(bytes(line))
        previous = line

    pixels = []
    for y in range(height):
        line = rows[y]
        for x in range(width):
            r, g, b = line[x * channels:x * channels + 3]
            a = line[x * channels + 3] if channels == 4 else 255
            pixels.append((r, g, b, a))
    return width, height, pixels


def load_banner(path):
    try:
        return read_png(path)
    except (OSError, ValueError, zlib.error) as error:
        print("banner %s not used: %s" % (path, error), flush=True)
        return None


def blend(buf, banner):
    """Alpha-blend a banner over the rendered frame, in place."""
    if not banner:
        return
    width, height, pixels = banner
    for y in range(min(height, H)):
        for x in range(min(width, W)):
            r, g, b, a = pixels[y * width + x]
            if a == 0:
                continue
            if a == 255:
                buf[y * W + x] = (r, g, b)
            else:
                dr, dg, db = buf[y * W + x]
                buf[y * W + x] = ((r * a + dr * (255 - a)) // 255,
                                  (g * a + dg * (255 - a)) // 255,
                                  (b * a + db * (255 - a)) // 255)


# The device locks an asset briefly while a draw reads it, so re-uploading the
# same name too soon can fail; rotate through a few filenames instead.
_RING = 4


class Sender:
    """Pushes frames from its own thread so a slow link never stalls rendering.

    Through the manager's cloud mode every request costs a full round trip to
    api.busy.app, so sending inline made the animation crawl and queue up. Here
    the render loop just drops its newest frame in a one-slot mailbox (stale
    ones are overwritten, never queued), and one keep-alive connection uploads
    and draws whatever is newest as fast as the link allows.
    """

    def __init__(self, base, text, font, priority, token=None):
        self.host = base.replace("http://", "").rstrip("/")
        self.text, self.font, self.priority, self.token = text, font, priority, token
        self.cond = threading.Condition()
        self.pending = None
        self.last = None
        self.closing = False
        self.error = None
        self.sent = self.dropped = self.frame_no = 0
        self.ready = None
        self.conns = [None, None]
        self.threads = [threading.Thread(target=self._run, daemon=True),
                        threading.Thread(target=self._draw, daemon=True)]
        for thread in self.threads:
            thread.start()

    def submit(self, pixels):
        with self.cond:
            if pixels == self.last:            # nothing changed: save the round trips
                return
            if self.pending is not None:
                self.dropped += 1
            self.pending = self.last = pixels
            self.cond.notify()

    def close(self):
        with self.cond:
            self.closing = True
            self.pending = self.ready = None
            self.cond.notify_all()
        for thread in self.threads:
            thread.join(timeout=6)

    def _request(self, slot, path, data, content_type):
        headers = {"Content-Type": content_type, "Content-Length": str(len(data))}
        if self.token:
            headers["X-API-Token"] = self.token
        for attempt in (0, 1):                 # a stale keep-alive socket: reconnect once
            try:
                if self.conns[slot] is None:
                    self.conns[slot] = http.client.HTTPConnection(self.host, timeout=8)
                self.conns[slot].request("POST", path, data, headers)
                reply = self.conns[slot].getresponse()
                reply.read()
                return reply.status
            except (OSError, http.client.HTTPException):
                self.conns[slot].close()
                self.conns[slot] = None
                if attempt:
                    raise

    def _run(self):
        """Stage 1: upload the newest frame, then hand its file name to stage 2."""
        while True:
            with self.cond:
                while self.pending is None and not self.closing:
                    self.cond.wait()
                if self.closing:
                    return
                pixels, self.pending = self.pending, None
            name = "frame%d.png" % (self.frame_no % _RING)
            self.frame_no += 1
            try:
                status = self._request(
                    0, "/api/assets/upload?application_name=%s&file=%s" % (APP, name),
                    _png(pixels), "application/octet-stream")
            except (OSError, http.client.HTTPException):
                time.sleep(0.5)                # link hiccup: the next frame will retry
                continue
            if status in (401, 403, 404):
                self.error = "HTTP %d on upload (token or route)" % status
            elif status < 400:                 # 508 = file still locked: skip this frame
                with self.cond:
                    self.ready = name          # a stale unsent name is simply replaced
                    self.cond.notify_all()

    def _draw(self):
        """Stage 2: draw the newest uploaded frame while stage 1 uploads the next."""
        while True:
            with self.cond:
                while self.ready is None and not self.closing:
                    self.cond.wait()
                if self.closing:
                    return
                name, self.ready = self.ready, None
            elements = [{"id": "frame", "type": "image", "path": name, "x": 0, "y": 0}]
            if self.text:
                elements.append({
                    "id": "label", "type": "text", "text": self.text,
                    "x": W // 2, "y": H // 2, "font": self.font, "align": "center",
                    "color": "#FFFFFFFF",
                })
            body = {"application_name": APP, "priority": self.priority, "elements": elements}
            try:
                status = self._request(1, "/api/display/draw", json.dumps(body).encode(),
                                       "application/json")
            except (OSError, http.client.HTTPException):
                time.sleep(0.5)
                continue
            self.sent += 1
            if status in (401, 403, 404):
                self.error = "HTTP %d on draw (token or route)" % status


class Controls:
    """The bar's wheel and START button, read from its state stream.

    /api/status/ws is a WebSocket that, once sent {"enable": true}, pushes
    protobuf `State` messages: mostly screen frames, plus an `input` update
    for every wheel step and button press. Nothing else in the HTTP API reports
    input, so a background thread keeps this stream open (pinging it, or the
    bar drops the client after ~10 s) and counts what comes in. If the stream
    is missing or fails, the animation simply runs without controls.
    """

    def __init__(self, host, token=None):
        self.host = host.replace("http://", "").rstrip("/")
        self.token = token
        self.lock = threading.Lock()
        self.steps = 0                         # wheel steps, either way, since the last take()
        self.starts = 0                        # START presses since the last take()
        self.clicks = 0                        # wheel clicks (the OK button) since then
        threading.Thread(target=self._run, daemon=True).start()

    def take(self):
        """(wheel steps, START presses, wheel clicks) since the previous call."""
        with self.lock:
            taken = self.steps, self.starts, self.clicks
            self.steps = self.starts = self.clicks = 0
        return taken

    def _run(self):
        while True:
            try:
                self._listen()
            except (OSError, EOFError, ValueError, IndexError):
                pass
            time.sleep(2)                      # bar unplugged or busy: try again

    def _listen(self):
        name, _, port = self.host.partition(":")
        sock = socket.create_connection((name, int(port or 80)), timeout=5)
        path = "/api/status/ws"
        if self.token:
            path += "?x-api-token=" + urllib.parse.quote(self.token, safe="")
        key = base64.b64encode(os.urandom(16)).decode()
        sock.sendall(("GET %s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\n"
                      "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
                      "Sec-WebSocket-Version: 13\r\n\r\n" % (path, self.host, key)).encode())
        reply = b""
        while b"\r\n\r\n" not in reply:
            chunk = sock.recv(1024)
            if not chunk:
                raise EOFError
            reply += chunk
        if b" 101 " not in reply.split(b"\r\n", 1)[0]:
            raise EOFError
        pending = reply.split(b"\r\n\r\n", 1)[1]

        def send(opcode, data):
            mask = os.urandom(4)
            size = bytes([0x80 | len(data)]) if len(data) < 126 else \
                bytes([0xFE]) + struct.pack(">H", len(data))
            sock.sendall(bytes([0x80 | opcode]) + size + mask
                         + bytes(c ^ mask[i % 4] for i, c in enumerate(data)))

        def read(n):
            nonlocal pending
            while len(pending) < n:
                chunk = sock.recv(65536)
                if not chunk:
                    raise EOFError
                pending += chunk
            out, pending = pending[:n], pending[n:]
            return out

        send(1, b'{"enable": true}')
        last_ping = time.monotonic()
        while True:
            if time.monotonic() - last_ping > 3:
                send(9, b"jam")
                last_ping = time.monotonic()
            sock.settimeout(0.5)
            try:
                head = read(2)
            except socket.timeout:
                continue
            sock.settimeout(5)
            size = head[1] & 0x7F
            if size == 126:
                size = struct.unpack(">H", read(2))[0]
            elif size == 127:
                size = struct.unpack(">Q", read(8))[0]
            payload = read(size)
            opcode = head[0] & 0x0F
            if opcode == 9:
                send(10, payload)
            elif opcode == 8:
                raise EOFError
            elif opcode == 2:
                self._count(payload)

    def _count(self, state):
        # State.updates (2) -> StateUpdate.input (11) -> InputEvent:
        # button_event (1) {button: OK 0 / BACK 1 / START 2, action: PRESS 0},
        # where OK is what the bar sends when the wheel is clicked;
        # encoder_event (3) {delta: sint32}
        for number, update in _proto_fields(state):
            if number != 2:
                continue
            for kind, event in _proto_fields(update):
                if kind != 11:
                    continue
                for which, body in _proto_fields(event):
                    values = dict(_proto_fields(body))
                    with self.lock:
                        if which == 1 and values.get(2, 0) == 0:     # a press
                            if values.get(1, 0) == 2:
                                self.starts += 1
                            elif values.get(1, 0) == 0:              # OK: the wheel's click
                                self.clicks += 1
                        elif which == 3:
                            raw = values.get(1, 0)
                            self.steps += abs((raw >> 1) ^ -(raw & 1))


def _proto_fields(data):
    """(field number, value) pairs of a protobuf message: ints for varints,
    bytes for everything else. Just enough to walk the state stream."""
    i = 0
    while i < len(data):
        key, i = _varint(data, i)
        number, wire = key >> 3, key & 7
        if wire == 0:
            value, i = _varint(data, i)
        elif wire == 1:
            value, i = data[i:i + 8], i + 8
        elif wire == 5:
            value, i = data[i:i + 4], i + 4
        elif wire == 2:
            length, i = _varint(data, i)
            value, i = data[i:i + length], i + length
        else:
            return
        yield number, value


def _varint(data, i):
    value = shift = 0
    while True:
        byte = data[i]
        i += 1
        value |= (byte & 0x7F) << shift
        shift += 7
        if byte < 0x80:
            return value, i


def clear(base, token=None):
    headers = {"X-API-Token": token} if token else {}
    request = urllib.request.Request(
        base + "/api/display/draw?application_name=" + APP, method="DELETE", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=5):
            pass
    except (urllib.error.HTTPError, urllib.error.URLError):
        pass


# ---------------------------------------------------------------------------
# Effects: each one fills a fresh 72x16 buffer from its own state
# ---------------------------------------------------------------------------

def blank():
    return [(0, 0, 0)] * (W * H)


def put(buf, x, y, rgb):
    if 0 <= x < W and 0 <= y < H:
        buf[y * W + x] = rgb


def plasma(buf, t):
    for y in range(H):
        for x in range(W):
            v = (math.sin(x / 7.0 + t)
                 + math.sin(y / 3.0 - t * 0.7)
                 + math.sin((x + y) / 6.0 + t * 1.3)
                 + math.sin(math.hypot(x - 36, (y - 8) * 2) / 5.0 - t))
            a = (v + 4) / 8.0
            buf[y * W + x] = (
                int(127 + 127 * math.sin(a * math.pi * 2)),
                int(127 + 127 * math.sin(a * math.pi * 2 + 2.1)),
                int(127 + 127 * math.sin(a * math.pi * 2 + 4.2)),
            )


_STARS = [{"x": random.uniform(-1, 1), "y": random.uniform(-1, 1), "z": random.uniform(0.05, 1)}

          for _ in range(90)]


def starfield(buf, t):
    for star in _STARS:
        star["z"] -= 0.035
        if star["z"] <= 0.02:
            star["x"] = random.uniform(-1, 1)
            star["y"] = random.uniform(-1, 1)
            star["z"] = 1.0
            continue
        px = int(36 + star["x"] / star["z"] * 26)
        py = int(8 + star["y"] / star["z"] * 7)
        bright = max(0.15, min(1.0, 1.15 - star["z"]))
        near = star["z"] < 0.25
        rgb = (int(255 * bright), int(255 * bright), int(255 * bright))
        put(buf, px, py, rgb)
        if near:  # close stars read as a 2x2 block
            put(buf, px + 1, py, rgb)
            put(buf, px, py + 1, rgb)
            put(buf, px + 1, py + 1, rgb)


_FIRE = [0.0] * (W * H)


def fire(buf, t):
    for x in range(W):
        _FIRE[(H - 1) * W + x] = random.uniform(0.55, 1.0)
    for y in range(H - 2, -1, -1):
        for x in range(W):
            below = _FIRE[(y + 1) * W + x]
            left = _FIRE[(y + 1) * W + max(0, x - 1)]
            right = _FIRE[(y + 1) * W + min(W - 1, x + 1)]
            value = (below * 2 + left + right) / 4.0 - 0.06
            _FIRE[y * W + x] = value if value > 0 else 0.0
    for i, heat in enumerate(_FIRE):
        if heat <= 0.01:
            continue
        if heat > 0.75:
            rgb = (255, 255, int(120 + 135 * heat))
        elif heat > 0.45:
            rgb = (255, int(60 + 340 * (heat - 0.45)), 0)
        else:
            rgb = (int(700 * heat), int(120 * heat), 0)
        buf[i] = (min(255, rgb[0]), min(255, rgb[1]), min(255, rgb[2]))


_SPARKS = []


def sparkle(buf, t):
    for _ in range(3):
        if random.random() < 0.55:
            _SPARKS.append({
                "x": random.randrange(W), "y": random.randrange(H),
                "vx": random.uniform(-0.4, 0.4), "vy": random.uniform(-0.35, 0.35),
                "life": random.randint(10, 28),
                "rgb": random.choice([(255, 60, 60), (255, 190, 40), (60, 255, 140),
                                      (80, 160, 255), (255, 80, 220), (255, 255, 255)]),
            })
    for s in _SPARKS:
        s["x"] += s["vx"]
        s["y"] += s["vy"]
        s["life"] -= 1
        fade = min(1.0, s["life"] / 8.0)
        rgb = tuple(int(c * fade) for c in s["rgb"])
        put(buf, int(round(s["x"])), int(round(s["y"])), rgb)
        if s["life"] % 4 == 0:  # twinkle bleed
            put(buf, int(round(s["x"])) - 1, int(round(s["y"])), tuple(c // 3 for c in rgb))
            put(buf, int(round(s["x"])) + 1, int(round(s["y"])), tuple(c // 3 for c in rgb))
    _SPARKS[:] = [s for s in _SPARKS if s["life"] > 0 and 0 <= s["y"] < H]


# ---------------------------------------------------------------------------
# The pool scene: a swimming pool seen from above
#
# The lettering is drawn here, pixel by pixel, from hand-made pixel fonts
# instead of being scaled down from the festival artwork: a downscale is what
# broke the title into unreadable letters. The title is a mosaic on the pool
# floor, in a bold 8x11 font that fills the bar. Each letter sways on its own as
# the surface bends the light, a glint sweeps across the word now and then, and
# pool toys drift over the whole pool — title included — with their shadows
# and wakes on the water.
# ---------------------------------------------------------------------------

# Small 5x7 fallback, for titles the big font cannot spell or fit.
FONT = {
    "A": (".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "C": (".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."),
    "E": ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    "F": ("#####", "#....", "#....", "####.", "#....", "#....", "#...."),
    "J": ("..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."),
    "M": ("#...#", "##.##", "#.#.#", "#...#", "#...#", "#...#", "#...#"),
    "N": ("#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"),
    "O": (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "S": (".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "U": ("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "0": (".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."),
    "2": (".###.", "#...#", "....#", "..##.", ".#...", "#....", "#####"),
    "6": ("..##.", ".#...", "#....", "####.", "#...#", "#...#", ".###."),
    " ": (".....", ".....", ".....", ".....", ".....", ".....", "....."),
}
FONT_H = 7
FONT_W = 5

# Bold 8x11 font, two-pixel strokes: what reads from across a jam room.
BIG_FONT = {
    "A": ("..####..", ".######.", "###..###", "##....##", "##....##", "########",
          "########", "##....##", "##....##", "##....##", "##....##"),
    "C": ("..######", ".#######", "###.....", "##......", "##......", "##......",
          "##......", "##......", "###.....", ".#######", "..######"),
    "E": ("########", "########", "##......", "##......", "######..", "######..",
          "##......", "##......", "##......", "########", "########"),
    "F": ("########", "########", "##......", "##......", "######..", "######..",
          "##......", "##......", "##......", "##......", "##......"),
    "J": ("..######", "..######", ".....##.", ".....##.", ".....##.", ".....##.",
          ".....##.", "##...##.", "###.###.", ".#####..", "..###..."),
    "M": ("##....##", "###..###", "########", "##.##.##", "##....##", "##....##",
          "##....##", "##....##", "##....##", "##....##", "##....##"),
    "N": ("##....##", "###...##", "###...##", "####..##", "##.##.##", "##.##.##",
          "##..####", "##...###", "##...###", "##....##", "##....##"),
    "O": ("..####..", ".######.", "###..###", "##....##", "##....##", "##....##",
          "##....##", "##....##", "###..###", ".######.", "..####.."),
    "S": (".#######", "########", "##......", "##......", "#######.", ".#######",
          "......##", "......##", "......##", "########", "#######."),
    "T": ("########", "########", "...##...", "...##...", "...##...", "...##...",
          "...##...", "...##...", "...##...", "...##...", "...##..."),
    "U": ("##....##", "##....##", "##....##", "##....##", "##....##", "##....##",
          "##....##", "##....##", "###..###", ".######.", "..####.."),
    "0": ("..####..", ".######.", "###..###", "##...###", "##..####", "##.##.##",
          "####..##", "###...##", "###..###", ".######.", "..####.."),
    "2": (".######.", "########", "##....##", "......##", ".....###", "...####.",
          ".####...", "###.....", "##......", "########", "########"),
    "6": ("..#####.", ".######.", "###.....", "##......", "#######.", "########",
          "##....##", "##....##", "###..###", ".######.", "..####.."),
    " ": ("....",) * 11,
}


def title_glyphs(text):
    """Text -> (glyphs, height): each glyph is (x offset, rows of 0/1).

    Uses the big font when it can spell the whole title and fit it with its
    outline; otherwise falls back to the small 5x7 font.
    """
    text = text.upper()
    font, height = BIG_FONT, 11
    big_width = sum(len(BIG_FONT[c][0]) + 1 for c in text if c in BIG_FONT) + 1
    if not all(c in BIG_FONT for c in text) or big_width > W:
        font, height = FONT, FONT_H
    glyphs, x = [], 0
    for char in text:
        glyph = font.get(char, font[" "])
        glyphs.append((x, [[1 if c == "#" else 0 for c in line] for line in glyph]))
        x += len(glyph[0]) + 1
    return glyphs, height


# Pool toys, seen from above, drawn heading right (mirrored heading left).
# Besides the classic duck and ring, inflatables that wink at video games.
# "." is transparent.
TOY_COLORS = {
    "Y": (255, 215, 30), "y": (220, 165, 10), "O": (255, 120, 0), "k": (20, 20, 20),
    "W": (255, 255, 255), "b": (30, 60, 230),
    "R": (235, 35, 45), "r": (160, 15, 25), "P": (255, 120, 140),
    "G": (70, 200, 70), "g": (40, 140, 45), "D": (15, 45, 20),
    "V": (120, 255, 120), "v": (40, 170, 60),
}
TOY_ART = {
    "duck": ("..YYYYYY........",
             ".YYyyyyYYY......",
             "YYYYYYYYYYYYYY..",
             "YYYYYYYYYYYYkYY.",
             "YYYYYYYYYYYYYYOO",
             "YYYYYYYYYYYYkYY.",
             "YYYYYYYYYYYYYY..",
             ".YYyyyyYYY......",
             "..YYYYYY........"),
    # a heart container, as found in caves
    "heart": (".RRR...RRR.",
              "RWWRR.RRRRR",
              "RWRRRRRRRRR",
              "RRRRRRRRRRr",
              ".RRRRRRRRr.",
              "..RRRRRRr..",
              "...RRRRr...",
              "....RRr....",
              ".....r....."),
    # the green fellow who hisses before he pops a pool float
    "creeper": ("GgGGVGGgGG",
                "GVGGgGGVGg",
                "GDDGGGGDDG",
                "gDDGgGGDDG",
                "GGGgDDGGVG",
                "GVGDDDDGgG",
                "GgGDDDDGGG",
                "GGGDGGDGVg",
                "gGVGGgGGGG",
                "GGGgGGVGgG"),
}
# Two-frame art, swapped as the toy goes: the invader marches.
TOY_FRAMES = {
    "invader": (("...V.....V...",
                 "....V...V....",
                 "...VVVVVVV...",
                 "..VVkVVVkVV..",
                 ".VVVVVVVVVVV.",
                 ".V.VVVVVVV.V.",
                 ".V.V.....V.V.",
                 "....VV.VV...."),
                ("...V.....V...",
                 ".V..V...V..V.",
                 ".V.VVVVVVV.V.",
                 ".VVVkVVVkVVV.",
                 ".VVVVVVVVVVV.",
                 "..VVVVVVVVV..",
                 "...V.....V...",
                 "..V.......V..")),
}
# Round toys are drawn from their radius so they can spin:
# (inner radius, outer radius, colours of the panels round the rim)
ROUND_TOYS = {
    "ring": (3.0, 6.4, [(235, 40, 45), (255, 255, 255)] * 4),
}
TETROMINOES = {                                # shape in blocks, and its colour
    "T": (("###", ".#."), (170, 60, 230)),
    "L": (("..#", "###"), (255, 140, 20)),
    "S": ((".##", "##."), (60, 210, 70)),
    "I": (("####",), (40, 210, 235)),
    "O": (("##", "##"), (250, 220, 30)),
}
GHOSTS = [(255, 40, 40), (255, 150, 210), (60, 220, 255), (255, 170, 60)]

# Every toy that can float by; the crossings take them in turn.
ROSTER = ["pacman", "duck", "mushroom", "goldring", "pokeball", "tetromino",
          "invader", "heart", "ring", "creeper"]
# The toys cross one after another, then leave the floor art clear for a while:
# second each slot sets off in the cycle, lane y, speed (px/s, sign = heading),
# sway amplitude, sway rate. Each cycle the slots take the next toys on the roster.
FLOTILLA = [
    (0.0, 8.0, 8.0, 1.5, 0.5),
    (8.0, 8.0, -8.5, 1.5, 0.7),
    (17.0, 8.0, 7.0, 2.0, 0.4),
]
TOY_CYCLE = 40.0                               # seconds; the last ~11 s are toy-free


def _disc(radius, colour_at):
    """Cells of a disc; colour_at(dx, dy, d) gives each pixel's colour (None = hole)."""
    cells, reach = [], int(math.ceil(radius))
    for dy in range(-reach, reach + 1):
        for dx in range(-reach, reach + 1):
            d = math.hypot(dx, dy)
            if d <= radius:
                colour = colour_at(dx, dy, d)
                if colour:
                    cells.append((dx, dy, colour))
    return cells


def _art(rows, heading, colours=TOY_COLORS, dx0=0):
    h, w = len(rows), len(rows[0])
    cells = []
    for row, line in enumerate(rows):
        for col, char in enumerate(line):
            if char == ".":
                continue
            u = col - (w - 1) // 2
            cells.append(((u if heading > 0 else -u) + dx0, row - (h - 1) // 2, colours[char]))
    return cells


def toy_pixels(name, heading, t, seed):
    """A toy's opaque pixels as (dx, dy, rgb) round its centre."""
    spin = t * (0.9 + 0.2 * (seed % 5)) * (1 if heading > 0 else -1)
    if name == "pacman":
        # chomping as he goes, a ghost hard on his heels
        mouth = 0.15 + 0.6 * abs(math.sin(t * 7))

        def pac(dx, dy, d):
            if dx > 0 and abs(math.atan2(dy, dx)) < mouth:
                return None
            if (dx, dy) == (0, -3):
                return (20, 20, 20)
            return (255, 220, 0)
        body = [((dx if heading > 0 else -dx), dy, c) for dx, dy, c in _disc(5.3, pac)]
        frame = int(t * 6) % 2
        ghost_rows = ("...####...", ".########.", "##########", "#WW###WW##",
                      "#Wb###Wb##", "##########", "##########", "##########",
                      "#.##.##.##" if frame else "##.##.##.#")
        colours = dict(TOY_COLORS, **{"#": GHOSTS[seed % len(GHOSTS)]})
        return body + _art(ghost_rows, heading, colours, dx0=-15 if heading > 0 else 15)
    if name == "mushroom":
        # the cap of a power-up mushroom: red, white spots, turning slowly
        spots = [(0.0, 0.0, 1.9)] + [(3.6 * math.cos(spin + k * math.pi / 2),
                                      3.6 * math.sin(spin + k * math.pi / 2), 1.3)
                                     for k in range(4)]

        def cap(dx, dy, d):
            if any(math.hypot(dx - sx, dy - sy) <= r for sx, sy, r in spots):
                return (255, 255, 255)
            return (160, 15, 25) if d > 4.6 else (230, 30, 40)
        return _disc(5.4, cap)
    if name == "goldring":
        # a big gold ring, a glint running round it
        def gold(dx, dy, d):
            if d < 2.8:
                return None
            glint = abs((math.atan2(dy, dx) - spin * 2 + math.pi) % (2 * math.pi) - math.pi)
            if glint < 0.35:
                return (255, 255, 230)
            if d < 3.6 or d > 5.0:
                return (150, 90, 0)            # dark rims, so it reads over the gold title
            return (255, 210, 50)
        return _disc(5.6, gold)
    if name == "pokeball":
        # red top, white bottom, black band and button, rocking on the water
        # (a full turn leaves the band jagged on the diagonals)
        rock = 0.35 * math.sin(t * 1.3 + seed)
        c, s = math.cos(rock), math.sin(rock)

        def ball(dx, dy, d):
            v = -dx * s + dy * c
            if d < 1.5:
                return (255, 255, 255)
            if d < 2.5 or abs(v) < 0.7 or d > 4.7:
                return (25, 25, 30)
            return (230, 30, 40) if v < 0 else (245, 245, 245)
        return _disc(5.3, ball)
    if name == "tetromino":
        shape, colour = TETROMINOES["TLSIO"[seed % 5]]
        light = tuple(min(255, int(ch * 1.35) + 40) for ch in colour)
        dark = tuple(int(ch * 0.6) for ch in colour)
        cells = []
        for by, line in enumerate(shape):
            for bx, on in enumerate(line):
                if on != "#":
                    continue
                for py in range(4):
                    for px in range(4):
                        shade = light if px == 0 or py == 0 else (dark if px == 3 or py == 3 else colour)
                        cells.append((bx * 4 + px - len(line) * 2, by * 4 + py - len(shape) * 2, shade))
        return cells
    if name in TOY_FRAMES:
        frames = TOY_FRAMES[name]
        return _art(frames[int(t * 3) % len(frames)], heading)
    if name in ROUND_TOYS:
        inner, outer, colours = ROUND_TOYS[name]
        panels = len(colours)

        def rim(dx, dy, d):
            if d < inner:
                return None
            return colours[int((math.atan2(dy, dx) + spin) / (2 * math.pi) * panels) % panels]
        return _disc(outer, rim)
    return _art(TOY_ART[name], heading)


def _hash01(x, y, n):
    """Cheap repeatable noise in 0..1 for (x, y, frame)."""
    h = (x * 374761393 + y * 668265263 + n * 2147483647) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return (h & 0xFFFF) / 65535.0


# The Stunfest logo, traced pixel by pixel from the official artwork
# (LOGO_STUN25_NB.svg). The original climbs steeply to the right; here it keeps
# a gentler climb of 3 pixels, letter by letter, so the word stays tall enough:
# "#" white lettering, "." the black badge, " " the pool floor showing through.
STUNFEST_LOGO = (
    "                                                            .........   ",
    "                                     .........              ..###....   ",
    "              .........              ..#####..              ..###....   ",
    "              ..###....              ..###...................#####..    ",
    "              ..###...................#####.#######.#######..#####..    ",
    "     ..........#####.###.###.#######..#####.#######.#######..###....    ",
    "    ..#######..#####.###.###.#######..###...##...##.###......###....    ",
    "    ..#######..###...###.###.###.###..###...#######.#######.###....     ",
    "    ..###......###...###.###.###.###.###...#######.#######..###....     ",
    "    ..#######.###...###.###.###.###..###...#######.#######..###....     ",
    "   ..#######..###...###.###.###.###..###...###.........###.#####..      ",
    "   ..#######..###...###.###.###.###.###...#######.#######..#####..      ",
    "   ......###.#####.#######.###.###..###...#######.#######.........      ",
    "  ..#######..#####.#######.###.###................................      ",
    "  ..#######................................................             ",
    "  ..................................                                    ",
)
LOGO_WHITE, LOGO_BLACK = (255, 255, 255), (26, 23, 27)
SWAP_FADE = 1.4                                # seconds a wave takes to swap title and logo
PUSH_PER_STEP = 0.07                           # how far one wheel step pushes the toys (0..1)
PUSH_HOLD = 1.2                                # seconds they stay aside after the wheel stops
PUSH_SETTLE = 0.3                              # then how fast they drift back, per second
PUSH_GLIDE = 0.35                              # seconds the toys take to catch up: no jumps
PUSH_REACH = 48                                # pixels a full push moves a toy towards its edge
RIPPLE_LIFE = 3.0                              # seconds a ring lasts as it spreads and fades
RIPPLE_SPEED = 15.0                            # how fast a ring spreads, pixels per second
RIPPLE_STRENGTH = 0.7                          # how bright a fresh ring is (0..1)
RIPPLE_EVERY = 0.3                             # at most one new ring per toy this often
THROW_FALL = 0.45                              # seconds a thrown toy takes to drop in
THROW_HEIGHT = 16                              # how far above its landing spot it starts
THROW_MAX = 3                                  # thrown toys in the pool at once
SPLASH_LIFE = 0.5                              # seconds the splash foam lasts


class PoolState:
    """What the pool shows, and how far the wheel has pushed the toys aside.

    `shown` is 0 for the title, 1 for the logo; `changed_at` is when it last
    changed (None before the first change, so the opening frame has no wave).
    """

    def __init__(self):
        self.shown, self.changed_at = 0, None
        self.push = 0.0                        # where the toys are, eased (0..1)
        self.aim = 0.0                         # where the wheel is sending them
        self.turned_at = -PUSH_HOLD
        self.stirred = False                   # the wheel moved since the last frame
        self.ripples = []                      # (x, y, born): rings spreading in the water
        self.rippled_at = {}                   # toy index -> when it last made a ring
        self.sides = {}                        # toy index -> edge (-1/1) it is being pushed to
        self.thrown = []                       # toys thrown in with a click of the wheel
        self.splashes = []                     # (x, y, at): foam where a thrown toy landed
        self.throws = 0                        # serial number, so each thrown toy is its own

    @classmethod
    def at(cls, t, swap):
        """The state a run without controls would be in at time t."""
        state = cls()
        if swap > 0 and t >= swap:
            state.shown, state.changed_at = int(t // swap) % 2, t // swap * swap
        return state

    def update(self, t, dt, steps, starts, swap, clicks=0):
        for _ in range(clicks):
            self.throw(t)
        self.stirred = bool(steps)
        if steps:
            self.aim, self.turned_at = min(1.0, self.aim + PUSH_PER_STEP * steps), t
        elif t - self.turned_at > PUSH_HOLD:
            self.aim = max(0.0, self.aim - PUSH_SETTLE * dt)
        # glide towards the aim rather than jumping a step at a time
        self.push += (self.aim - self.push) * (1.0 - math.exp(-dt / PUSH_GLIDE))
        since = t - (self.changed_at if self.changed_at is not None else 0.0)
        if starts or (swap > 0 and since >= swap):
            self.shown, self.changed_at = 1 - self.shown, t


    def throw(self, t):
        """Drop a random toy into the middle of the pool; it drifts off after."""
        if len(self.thrown) >= THROW_MAX:
            self.thrown.pop(0)
        self.throws += 1
        heading = random.choice((-1, 1))
        self.thrown.append({
            "name": random.choice(ROSTER),
            "x": (W - 1) / 2 + random.uniform(-8, 8), "y": (H - 1) / 2 + random.uniform(-1, 1),
            "vx": heading * random.uniform(3.5, 6.0), "vy": random.uniform(-0.6, 0.6),
            "lands": t + THROW_FALL, "key": "thrown%d" % self.throws, "seed": self.throws,
        })


def ripple(source, t, calm=1.0):
    """The surface bends what lies on the floor a little, only where a swell
    rolls across it every few seconds; the rest of the time it stays crisp.

    Only rows slide, and only at the crest of the swell: a slight kink that
    comes and goes.
    """
    swell_x = (t % 4.0) / 4.0 * (W + 30) - 15
    out = [None] * (W * H)
    for y in range(H):
        for x in range(W):
            amp = calm * (0.505 + 0.23 * math.exp(-((x - swell_x) / 9.0) ** 2))
            sx = int(round(x - amp * math.sin(y * 0.5 + x * 0.05 + t * 2.4)))
            if 0 <= sx < W:
                out[y * W + x] = source[y * W + sx]
    return out


def title_layer(t, title):
    """The title in the floor: each letter sways as one block (a per-row shift
    shears the glyphs until T, J, A and M lose their shape), sunny yellow at the
    top of each letter, warm orange at the foot. The 5x7 fallback has one-pixel
    strokes that break easily, so it gets a gentler ripple."""
    glyphs, glyph_h = title_glyphs(title)
    span = glyphs[-1][0] + len(glyphs[-1][1][0]) if glyphs else 0
    left = (W - span) // 2
    top = (H - glyph_h) // 2
    source = [None] * (W * H)
    for i, (gx, rows) in enumerate(glyphs):
        lift = int(round(0.75 * math.sin(t * 2.2 - i * 0.8)))
        for gy, line in enumerate(rows):
            y = top + gy + lift
            depth = gy / max(1, glyph_h - 1)
            colour = (255, int(238 - 70 * depth), int(120 - 95 * depth))
            for col, on in enumerate(line):
                x = left + gx + col
                if on and 0 <= x < W and 0 <= y < H:
                    source[y * W + x] = colour
    return ripple(source, t, 1.0 if glyph_h > FONT_H else 0.8)


def logo_layer(t):
    """The Stunfest logo laid in the pool floor. It holds still apart from the
    same ripple as the title: the slits inside its letters are one pixel thin,
    and moving whole columns closed them up."""
    source = [None] * (W * H)
    for y in range(H):
        for x in range(W):
            cell = STUNFEST_LOGO[y][x]
            if cell == "#":
                source[y * W + x] = LOGO_WHITE
            elif cell == ".":
                source[y * W + x] = LOGO_BLACK
    return ripple(source, t)


def ripple_rings(ripples, t):
    """For each pixel: (ring strength 0..1, x and y step away from the centre),
    or None when the water is still. A ring is a thin bright band that spreads
    out from where a toy was shoved and fades as it goes."""
    if not ripples:
        return None
    field = [(0.0, 0, 0)] * (W * H)
    for rx, ry, born in ripples:
        age = t - born
        if age < 0:
            continue                           # a ring due a moment later
        radius = 1.5 + RIPPLE_SPEED * age
        fade = RIPPLE_STRENGTH * (1.0 - age / RIPPLE_LIFE)
        for y in range(max(0, int(ry - radius - 2)), min(H, int(ry + radius + 3))):
            for x in range(max(0, int(rx - radius - 2)), min(W, int(rx + radius + 3))):
                if abs(y - ry) < radius - 7 and abs(x - rx) < radius - 7:
                    continue                   # well inside the ring: still water
                d = math.hypot(x - rx, y - ry)
                # a leading crest, and a weaker one following four pixels behind
                band = max(1.0 - abs(d - radius) / 1.5,
                           0.5 * (1.0 - abs(d - radius + 4.0) / 1.5))
                if band <= 0:
                    continue
                strength = fade * band
                i = y * W + x
                if strength > field[i][0]:
                    reach = 2.0 if strength > 0.45 else 1.0   # fresh crests bend further
                    field[i] = (strength, int(round(reach * (x - rx) / max(d, 1.0))),
                                int(round(reach * (y - ry) / max(d, 1.0))))
    return field


def pool(buf, t, title="OCTOJAM", state=None):
    """A swimming pool seen from above, the title laid in the floor, taking
    turns with the Stunfest logo as `state` says.

    Each change rolls in as a wave sweeping left to right, foam on its crest.
    Every letter keeps a dark outline so the caustics cannot eat into it. The
    toys are free to float over it all: they are small and keep moving, so the
    word is always readable a moment later.
    """
    state = state or PoolState()

    # the toys, drifting across the pool
    toys = []
    for k, (start, lane, speed, sway, rate) in enumerate(FLOTILLA):
        # enter just off one edge, cross, then wait off-screen for the next cycle,
        # coming back as the next toy on the roster
        cycle = int((t - start) // TOY_CYCLE)
        name = ROSTER[(cycle * len(FLOTILLA) + k) % len(ROSTER)]
        travelled = ((t - start) % TOY_CYCLE) * abs(speed) - 9
        x = travelled if speed > 0 else W - 1 - travelled
        # the wheel shoves them towards the nearer edge, clearing the floor art.
        # The edge is picked once, when the shove starts: picking it afresh
        # each frame flipped a toy across the screen as it passed the middle.
        if state.aim == 0 and state.push < 0.01:
            state.sides.pop(k, None)
        elif k not in state.sides:
            state.sides[k] = -1 if x < (W - 1) / 2 else 1
        eased = state.push * state.push * (3 - 2 * state.push)
        x += state.sides.get(k, 0) * PUSH_REACH * eased
        y = lane + sway * math.sin(t * rate + k * 1.3)
        cx, cy = int(round(x)), int(round(y))
        toys.append((cx, cy, speed, [(cx + u, cy + v, rgb)
                                     for u, v, rgb in toy_pixels(name, speed, t, cycle * len(FLOTILLA) + k)], 0))
        # a shoved toy sends rings out across the water
        if state.stirred and -4 <= cx < W + 4 and \
                t - state.rippled_at.get(k, -RIPPLE_EVERY) >= RIPPLE_EVERY:
            state.ripples.append((cx, cy, t))
            state.rippled_at[k] = t
    # toys thrown in with a click of the wheel: they drop in from above, their
    # shadow waiting where they will land, then splash and drift off
    for toy in list(state.thrown):
        afloat = t - toy["lands"]
        lift = 0
        if afloat < 0:
            lift = int(round(THROW_HEIGHT * (-afloat / THROW_FALL) ** 1.6))
            x, y, heading = toy["x"], toy["y"], toy["vx"]
        else:
            if not toy.get("splashed"):
                toy["splashed"] = True
                state.splashes.append((toy["x"], toy["y"], t))
                state.ripples += [(toy["x"], toy["y"], t), (toy["x"], toy["y"], t + 0.25)]
            x, y, heading = toy["x"] + toy["vx"] * afloat, toy["y"] + toy["vy"] * afloat, toy["vx"]
            y = max(2.0, min(H - 3.0, y))
            key = toy["key"]
            if state.aim == 0 and state.push < 0.01:
                state.sides.pop(key, None)
            elif key not in state.sides:
                state.sides[key] = -1 if x < (W - 1) / 2 else 1
            eased = state.push * state.push * (3 - 2 * state.push)
            x += state.sides.get(key, 0) * PUSH_REACH * eased
            if not -16 < x < W + 16:
                state.thrown.remove(toy)       # drifted out of the pool
                state.sides.pop(key, None)
                continue
        cx, cy = int(round(x)), int(round(y))
        toys.append((cx, cy - lift, heading if afloat >= 0 else 0,
                     [(cx + u, cy - lift + v, rgb)
                      for u, v, rgb in toy_pixels(toy["name"], heading, t, toy["seed"])],
                     lift))
    state.splashes = [s for s in state.splashes if t - s[2] < SPLASH_LIFE]
    state.ripples = [r for r in state.ripples if t - r[2] < RIPPLE_LIFE]
    ring = ripple_rings(state.ripples, t)

    layers = {0: lambda: title_layer(t, title), 1: lambda: logo_layer(t)}
    shown = layers[state.shown]()
    into = t - state.changed_at if state.changed_at is not None else SWAP_FADE
    foam = set()
    if into < SWAP_FADE:
        before = layers[1 - state.shown]()
        front = into / SWAP_FADE * (W + 16) - 8
        mixed = [None] * (W * H)
        for y in range(H):
            for x in range(W):
                # the crest churns: rows there slide by up to two pixels
                near = abs(x - front) < 3
                sx = x + int(round(2 * math.sin(y * 1.1 + t * 9))) if near else x
                sx = max(0, min(W - 1, sx))
                mixed[y * W + x] = (shown if sx < front else before)[y * W + sx]
                if near:
                    foam.add((x, y))
        shown = mixed
    if ring:
        # where a ring passes, the floor art bends a pixel away from its centre
        bent = list(shown)
        for i, (strength, ox, oy) in enumerate(ring):
            if strength > 0.18:
                sx, sy = i % W - ox, i // W - oy
                if 0 <= sx < W and 0 <= sy < H:
                    bent[i] = shown[sy * W + sx]
        shown = bent
    letter = [colour is not None for colour in shown]

    # now and then a glint sweeps across the floor art, on a slant
    phase = (t % 5.0) / 1.2                    # the sweep itself lasts 1.2 s
    glint_x = -6 + phase * (W + 12) if phase <= 1.0 else -100

    for y in range(H):
        for x in range(W):
            i = y * W + x
            # the floor seen through a moving surface: the tile grid wavers
            fx = x + 0.55 * math.sin(y * 0.9 + t * 2.1) + 0.3 * math.sin(x * 0.21 - t * 1.3)
            fy = y + 0.45 * math.sin(x * 0.47 + t * 1.7)
            grout = (fx % 6.0) < 0.6 or (fy % 6.0) < 0.6
            # caustics: the bright net of light focused by the waves
            a = math.sin(x * 0.33 + 1.6 * math.sin(y * 0.52 + t * 0.9) + t * 0.8)
            b = math.sin(y * 0.61 + 1.4 * math.sin(x * 0.24 - t * 0.7) - t * 0.6)
            net = max(0.0, 1.0 - abs(a + b) * 1.4) ** 3

            if letter[i]:
                r, g, b_ = shown[i]
                light = 0.9 + 0.35 * net
                if shown[i] == LOGO_WHITE:
                    light = 1.0                # dimming the logo's white speckles it
                if ring:
                    light += 0.45 * ring[i][0]
                if abs((x - y * 0.6) - glint_x) < 1.6:
                    light = 1.6                # the glint
                buf[i] = (min(255, int(r * light)), min(255, int(g * light)),
                          min(255, int(b_ * light)))
            elif any(letter[(y + dy) * W + x + dx]
                     for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                     if 0 <= x + dx < W and 0 <= y + dy < H):
                buf[i] = (3, 14, 32)           # full outline, keeps the word legible
            else:
                base = (14, 82, 135) if grout else (20, 104, 160)
                if ring:
                    net += ring[i][0]          # a passing ring catches the light
                buf[i] = (min(255, int(base[0] + 110 * net)),
                          min(255, int(base[1] + 125 * net)),
                          min(255, int(base[2] + 90 * net)))
            if (x, y) in foam and _hash01(x, y, int(t * 15)) > 0.45:
                buf[i] = (215, 240, 250)       # foam on the crest of the swap wave

    # the toys' wakes, a pale V trailing behind each one
    for cx, cy, speed, cells, lift in toys:
        if lift or not speed:
            continue                           # still in the air: no wake yet
        back = -1 if speed > 0 else 1
        tail = (min if speed > 0 else max)(x for x, _, _ in cells)
        for step in range(1, 5):
            fade = 1.0 - step / 5.0
            for wy in (cy - step // 2, cy + step // 2):
                wx = tail + back * step
                if 0 <= wx < W and 0 <= wy < H and not letter[wy * W + wx]:
                    r, g, b = buf[wy * W + wx]
                    buf[wy * W + wx] = (min(255, int(r + 70 * fade)), min(255, int(g + 80 * fade)),
                                        min(255, int(b + 70 * fade)))

    # their shadows, cast down-right onto the floor (and the letters)
    shaded = set()
    for _, _, _, cells, lift in toys:
        for x, y, _ in cells:
            shaded.add((x + 2, y + 2 + lift))
    for x, y in shaded:
        if 0 <= x < W and 0 <= y < H:
            r, g, b = buf[y * W + x]
            buf[y * W + x] = (r * 40 // 100, g * 40 // 100, b * 48 // 100)

    # the sun glinting off the surface
    frame = int(t * 10)
    for y in range(H):
        for x in range(W):
            if not letter[y * W + x] and _hash01(x, y, frame) > 0.994:
                buf[y * W + x] = (235, 250, 255)

    # splash foam, a broken white ring bursting out where a thrown toy landed
    for sx, sy, at in state.splashes:
        age = (t - at) / SPLASH_LIFE
        radius = 3 + 6 * age
        for y in range(H):
            for x in range(max(0, int(sx - radius - 2)), min(W, int(sx + radius + 3))):
                if abs(math.hypot(x - sx, (y - sy) * 1.2) - radius) < 1.2 and \
                        _hash01(x, y, int(t * 20)) > 0.35 + 0.5 * age:
                    buf[y * W + x] = (225, 245, 255)

    for _, _, _, cells, _ in toys:
        for x, y, rgb in cells:
            put(buf, x, y, rgb)


EFFECTS = {"plasma": plasma, "starfield": starfield, "fire": fire, "sparkle": sparkle}
POOL = "pool"
# auto cycles the abstract effects; the pool scene carries the title, so it is
# never part of the rotation — you either show the title or you don't.
ORDER = ["starfield", "plasma", "fire", "sparkle"]


def render(effect, t, chunk_seconds, title="OCTOJAM", swap=60.0, state=None):
    buf = blank()
    if effect == "auto":
        name = ORDER[int(t / chunk_seconds) % len(ORDER)]
    else:
        name = effect
    if name == POOL:
        pool(buf, t, title, state or PoolState.at(t, swap))
    else:
        EFFECTS[name](buf, t)
    return buf


def parse_args():
    parser = argparse.ArgumentParser(description="BUSY Bar jam show-off animations")
    parser.add_argument("--host", default="10.0.4.20", help="BUSY Bar host[:port]")
    parser.add_argument("--effect", default=POOL,
                        choices=sorted(EFFECTS) + ["auto", POOL],
                        help="effect to play, or auto to cycle them")
    parser.add_argument("--title", default="OCTOJAM",
                        help="title drawn by the pool scene")
    parser.add_argument("--swap", type=float, default=60.0,
                        help="pool: seconds between title and Stunfest logo "
                             "(0 = only when START is pressed)")
    parser.add_argument("--text", default="", help="banner text (empty for none)")
    parser.add_argument("--font", default="normal", help="text: normal|bold|large|extra_large|...")
    parser.add_argument("--live", action="store_true",
                        help="pool: render and push every frame instead of playing the "
                             "pre-rendered loop (needed for the wheel and START controls)")
    parser.add_argument("--loop", default=None,
                        help="pre-rendered .anim to play (default: loops/<title>_72x16.anim)")
    parser.add_argument("--fps", type=float, default=15.0, help="draw updates per second")
    parser.add_argument("--priority", type=int, default=50, help="draw priority 1-100")
    parser.add_argument("--chunk", type=float, default=6.0,
                        help="seconds per effect in auto mode")
    parser.add_argument("--banner", default=None,
                        help="PNG (<=72x16) drawn over the effect; defaults to "
                             "banner.png next to this file")
    parser.add_argument("--seconds", type=float, default=0.0,
                        help="stop after N seconds (0 = run until Ctrl-C)")
    parser.add_argument("--token", default=None,
                        help="Wi-Fi API password; prefer the BUSYBAR_TOKEN env var "
                             "to keep it out of the shell history")
    return parser.parse_args()


def play_loop(base, paths, swap, priority, token=None):
    """Upload pre-rendered .anim loops once and let the bar play them by itself.

    One upload per loop and one tiny draw every swap, whatever the link: no
    per-frame traffic, so the cloud's round-trip time no longer matters. With
    several loops and swap > 0 they take turns every `swap` seconds.
    """
    for path in paths:
        with open(path, "rb") as handle:
            data = handle.read()
        while True:
            try:
                post(base, "/api/assets/upload?application_name=%s&file=%s"
                     % (APP, os.path.basename(path)), data, "application/octet-stream", token,
                     timeout=60)           # a 250 KB file over the cloud can take a while
                break
            except urllib.error.HTTPError as error:
                if error.code in (401, 403, 404, 413):
                    sys.exit("error: upload refused (HTTP %d)" % error.code)
                time.sleep(1)
            except OSError:                    # URLError, timeouts: try again
                time.sleep(2)
    started, shown = time.monotonic(), None
    while True:
        turn = int((time.monotonic() - started) // swap) % len(paths) \
            if swap > 0 and len(paths) > 1 else 0
        if turn != shown:                      # re-sending an identical element would restart it
            body = json.dumps({"application_name": APP, "priority": priority, "elements": [
                {"id": "loop%d" % turn, "type": "animation",
                 "path": os.path.basename(paths[turn]), "x": 0, "y": 0, "loop": True}]}).encode()
            try:
                if shown is not None:          # the bar keeps a playing animation unless cleared
                    clear(base, token)
                post(base, "/api/display/draw", body, "application/json", token)
                shown = turn
            except urllib.error.HTTPError as error:
                if error.code != 409:          # 409 = a higher-priority app owns the display
                    raise
            except OSError:
                pass
        time.sleep(1)


def main():
    args = parse_args()
    if args.fps <= 0:
        raise SystemExit("--fps must be greater than zero")
    if not 1 <= args.priority <= 100:
        raise SystemExit("--priority must be between 1 and 100")
    token = args.token or os.environ.get("BUSYBAR_TOKEN") or None
    if args.token:
        print("note: --token is visible in the process list; BUSYBAR_TOKEN is safer.",
              flush=True)
    base = endpoint(args.host)
    frame_time = 1.0 / args.fps
    loops_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "loops")
    loop_files = [args.loop] if args.loop else [
        os.path.join(loops_dir, "%s_72x16.anim" % name) for name in (args.title.lower(), "stunfest")]
    loop_files = [f for f in loop_files if os.path.exists(f)]
    if args.effect == POOL and not args.live and loop_files:
        print("%s -> %s loops=%s swap=%gs (Ctrl-C to stop)"
              % (APP, base, [os.path.basename(f) for f in loop_files], args.swap), flush=True)
        try:
            play_loop(base, loop_files, args.swap, args.priority, token)
        except KeyboardInterrupt:
            print("\nstopped.", flush=True)
        except urllib.error.HTTPError as error:
            sys.exit("error: HTTP %s — %s" % (error.code, error.read().decode("utf-8", "ignore")))
        finally:
            clear(base, token)
        return
    started = time.monotonic()
    banner_path = args.banner or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                              "banner.png")
    banner = load_banner(banner_path) if os.path.exists(banner_path) else None
    if banner:
        print("banner: %s (%dx%d)"
              % (banner_path, banner[0], banner[1]), flush=True)
    print("%s -> %s effect=%s text=%r fps=%g auth=%s (Ctrl-C to stop)"
          % (APP, base, args.effect, args.text, args.fps, "token" if token else "none"),
          flush=True)
    controls = Controls(args.host, token) if args.effect == POOL else None
    sender = Sender(base, args.text, args.font, args.priority, token)
    state, previous = PoolState(), 0.0
    try:
        while True:
            t = time.monotonic() - started
            if args.seconds and t >= args.seconds:
                break
            cycle = time.monotonic()
            if controls:
                steps, starts, clicks = controls.take()
                state.update(t, t - previous, steps, starts, args.swap, clicks)
                if starts:
                    print("START -> %s" % ("logo" if state.shown else "title"), flush=True)
            previous = t
            frame = render(args.effect, t, args.chunk, args.title, args.swap, state)
            if args.effect != POOL:
                # the pool scene draws the title itself; layering a banner on
                # top of it is what used to break the lettering
                blend(frame, banner)
            sender.submit(frame)
            if sender.error:
                sys.exit("error: " + sender.error)
            delay = frame_time - (time.monotonic() - cycle)
            if delay > 0:
                time.sleep(delay)
    except KeyboardInterrupt:
        print("\nstopped.", flush=True)
    except urllib.error.HTTPError as error:
        sys.exit("error: HTTP %s — %s" % (error.code, error.read().decode("utf-8", "ignore")))
    except urllib.error.URLError as error:
        sys.exit("error: cannot reach %s — %s" % (base, error.reason))
    finally:
        sender.close()
        clear(base, token)


if __name__ == "__main__":
    main()
