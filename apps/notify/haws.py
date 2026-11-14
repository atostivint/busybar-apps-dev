"""Home Assistant events over its WebSocket API, in standard-library Python only.

HA pushes the custom event `busybar_notify`; an automation fires it with
`action: event.fire` (see the README). This module keeps that subscription open in a background
thread: it authenticates with a long-lived token, subscribes, then hands every event's payload to
`on_event(data)` as {"kind", "title", "message"}. It pings the socket every ~20 s, and reconnects
with a doubling backoff on anything that goes wrong (socket error, HA restart, token refused).

URL and token come from HA_URL / HA_TOKEN (or the flags that default to them): nothing is stored
in a file, and the token is never printed. The framing is the same hand-rolled one as buttons.py:
a blocking socket, masked frames out, whole messages in.
"""
import base64
import json
import os
import socket
import ssl
import struct
import sys
import threading
import time
import urllib.parse

EVENT = "busybar_notify"  # the custom event HA fires
PING_S = 20  # seconds of silence before a websocket ping (HA drops idle clients)
TIMEOUT_S = 15  # connect + handshake
MAX_BACKOFF_S = 60


class AuthError(Exception):
    """The token or the subscription was refused: retrying quickly will not help."""


def config(url=None, token=None):
    """-> (url, token) from the arguments, else HA_URL / HA_TOKEN; None unless both are set."""
    url = (url or os.environ.get("HA_URL", "")).strip().rstrip("/")
    token = (token or os.environ.get("HA_TOKEN", "")).strip()
    return (url, token) if url and token else None


def parse_event(data):
    """An event payload -> {"kind", "title", "message", "source"}, or None when it is not an object.

    kind defaults to "generic", the other fields to "". Numbers are stringified (an automation may
    well send `kind: 3`), and surrounding whitespace is dropped. `source` is the short camera or
    place name the alert screen shows; when it is empty the screen falls back to `title`.
    """
    if not isinstance(data, dict):
        return None

    def field(name):
        v = data.get(name)
        if isinstance(v, str):
            return v.strip()
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return str(v)
        return ""

    return {"kind": field("kind") or "generic", "title": field("title"),
            "message": field("message"), "source": field("source")}


def ws_url(url):
    """http(s)://host[:port] -> ws(s)://host[:port]/api/websocket (an already-WS URL is kept)."""
    url = str(url).strip().rstrip("/")
    for scheme, ws in (("https://", "wss://"), ("http://", "ws://"), ("wss://", "wss://"), ("ws://", "ws://")):
        if url.startswith(scheme):
            url = ws + url[len(scheme):]
            break
    else:
        url = "ws://" + url
    return url if url.endswith("/api/websocket") else url + "/api/websocket"


def _parts(url):
    p = urllib.parse.urlsplit(url)
    secure = p.scheme == "wss"
    if not p.hostname:
        raise ValueError(f"no host in {url!r}")
    path = p.path or "/"
    if p.query:
        path += "?" + p.query
    return p.hostname, p.port or (443 if secure else 80), path, secure


class _Frames:
    """WebSocket frames over a blocking socket: whole messages in, masked frames out.

    A read that hits its deadline leaves whatever arrived in `buf` and returns None, so the caller
    can ping and read again without losing sync: nothing is consumed until a frame is complete.
    """

    def __init__(self, sock):
        self.sock = sock
        self.buf = b""
        self.op = None  # opcode of the fragmented message in progress
        self.parts = []

    def _need(self, n, timeout):
        deadline = time.monotonic() + timeout
        while len(self.buf) < n:
            left = deadline - time.monotonic()
            if left <= 0:
                return False
            self.sock.settimeout(left)
            try:
                chunk = self.sock.recv(65536)
            except (socket.timeout, TimeoutError):
                # No data before the deadline. This is not a disconnect: the caller pings and reads
                # again, and nothing has been consumed from `buf` (a partial frame stays complete-able).
                if time.monotonic() >= deadline:
                    return False
                continue
            if not chunk:
                raise EOFError("connection closed")  # a real EOF must still be fatal
            self.buf += chunk
        return True

    def read_frame(self, timeout):
        """-> (fin, opcode, payload), or None on timeout."""
        if not self._need(2, timeout):
            return None
        b0, b1 = self.buf[0], self.buf[1]
        fin, opcode = b0 & 0x80, b0 & 0x0F
        masked, size = b1 & 0x80, b1 & 0x7F
        head = 2
        if size == 126:
            if not self._need(head + 2, timeout):
                return None
            size, head = struct.unpack(">H", self.buf[2:4])[0], 4
        elif size == 127:
            if not self._need(head + 8, timeout):
                return None
            size, head = struct.unpack(">Q", self.buf[2:10])[0], 10
        mask = b""
        if masked:
            if not self._need(head + 4, timeout):
                return None
            mask, head = self.buf[head:head + 4], head + 4
        if not self._need(head + size, timeout):
            return None
        payload, self.buf = self.buf[head:head + size], self.buf[head + size:]
        if mask:
            payload = bytes(c ^ mask[i % 4] for i, c in enumerate(payload))
        return fin, opcode, payload

    def read_message(self, timeout):
        """-> (opcode, payload) for one whole data message, or None on timeout.

        Control frames are handled here: a ping is answered, a close raises EOFError. Continuation
        frames are collected until the message ends.
        """
        deadline = time.monotonic() + timeout
        while True:
            left = deadline - time.monotonic()
            frame = self.read_frame(max(left, 0.01)) if left > 0 else None
            if frame is None:
                return None
            fin, opcode, payload = frame
            if opcode == 9:  # ping
                self.send(10, payload)
            elif opcode in (0, 1, 2):
                if opcode:
                    self.op, self.parts = opcode, [payload]
                elif self.op is not None:  # continuation of the message in progress
                    self.parts.append(payload)
                if self.op is not None and fin:
                    op, data = self.op, b"".join(self.parts)
                    self.op, self.parts = None, []
                    return op, data
            elif opcode == 8:
                raise EOFError("connection closed by the peer")

    def send(self, opcode, data):
        mask = os.urandom(4)
        n = len(data)
        if n < 126:
            head = bytes([0x80 | opcode, 0x80 | n])
        elif n < 65536:
            head = bytes([0x80 | opcode, 0x80 | 126]) + struct.pack(">H", n)
        else:
            head = bytes([0x80 | opcode, 0x80 | 127]) + struct.pack(">Q", n)
        self.sock.sendall(head + mask + bytes(c ^ mask[i % 4] for i, c in enumerate(data)))


def connect(url, timeout=TIMEOUT_S):
    """Opens the WebSocket and checks the upgrade; returns a _Frames."""
    host, port, path, secure = _parts(ws_url(url))
    sock = socket.create_connection((host, port), timeout=timeout)
    if secure:
        sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
    key = base64.b64encode(os.urandom(16)).decode()
    sock.sendall((f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n"
                  f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                  f"Sec-WebSocket-Version: 13\r\n\r\n").encode())
    reply = b""
    while b"\r\n\r\n" not in reply:
        chunk = sock.recv(4096)
        if not chunk:
            raise EOFError("no handshake reply")
        reply += chunk
    status = reply.split(b"\r\n", 1)[0]
    if b" 101 " not in status:
        raise OSError(f"handshake refused: {status[:80].decode('latin-1')!r}")
    frames = _Frames(sock)
    frames.buf = reply.split(b"\r\n\r\n", 1)[1]  # HA may already have sent auth_required
    return frames


class HAWebSocket:
    """Subscribes to `event` and calls on_event(data) for each one, in its own thread."""

    def __init__(self, on_event, url, token, event=EVENT):
        self.on_event = on_event
        self.url = url
        self.token = token  # never printed
        self.event = event
        self.frames = None
        self._stop = threading.Event()
        self._thread = None
        self._backoff = 1

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def stop(self, timeout=3):
        self._stop.set()
        frames = self.frames
        if frames is not None:
            try:
                frames.sock.close()  # unblocks the read in the other thread
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout)

    def _run(self):
        while not self._stop.is_set():
            try:
                self._session()
                if self._stop.is_set():
                    break
                raise EOFError("connection closed")
            except AuthError as e:
                print(f"home assistant: {e}; retrying in {MAX_BACKOFF_S} s", file=sys.stderr, flush=True)
                self._backoff = MAX_BACKOFF_S
            except (OSError, EOFError, ValueError) as e:
                if self._stop.is_set():
                    break
                print(f"home assistant: {e}; reconnecting in {self._backoff} s", file=sys.stderr, flush=True)
                self._backoff = min(self._backoff * 2, MAX_BACKOFF_S)
            except Exception as e:  # anything unforeseen must not kill the listener for good
                if self._stop.is_set():
                    break
                print(f"home assistant: {type(e).__name__}: {e}; reconnecting in {self._backoff} s",
                      file=sys.stderr, flush=True)
                self._backoff = min(self._backoff * 2, MAX_BACKOFF_S)
            self._stop.wait(self._backoff)

    def _session(self):
        frames = connect(self.url)
        self.frames = frames
        try:
            hello = self._json(frames, TIMEOUT_S)
            if hello.get("type") == "auth_required":
                frames.send(1, json.dumps({"type": "auth", "access_token": self.token}).encode())
                reply = self._json(frames, TIMEOUT_S)
                if reply.get("type") != "auth_ok":
                    raise AuthError("authentication refused (check HA_TOKEN)")
            elif hello.get("type") != "auth_ok":
                raise ValueError(f"unexpected first message {hello.get('type')!r}")
            frames.send(1, json.dumps({"id": 1, "type": "subscribe_events",
                                       "event_type": self.event}).encode())
            reply = self._json(frames, TIMEOUT_S)
            if not reply.get("success"):
                raise AuthError(f"subscription refused: {reply.get('error')}")
            self._backoff = 1
            host, port, _, _ = _parts(ws_url(self.url))
            print(f"home assistant: connected to {host}:{port}, listening for {self.event}",
                  file=sys.stderr, flush=True)
            while not self._stop.is_set():
                message = frames.read_message(PING_S)
                if message is None:
                    frames.send(9, b"notify")  # keep the websocket alive
                    continue
                opcode, payload = message
                if opcode != 1:
                    continue
                try:
                    msg = json.loads(payload.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    continue
                if msg.get("type") == "event":
                    data = (msg.get("event") or {}).get("data")
                    try:
                        self.on_event(data)
                    except Exception as e:  # a bad alert must never kill the listener
                        print(f"home assistant: on_event failed: {e}", file=sys.stderr, flush=True)
        finally:
            try:
                frames.sock.close()
            except OSError:
                pass
            if self.frames is frames:
                self.frames = None

    @staticmethod
    def _json(frames, timeout):
        message = frames.read_message(timeout)
        if message is None:
            raise TimeoutError("no reply from home assistant")
        opcode, payload = message
        if opcode != 1:
            raise ValueError(f"unexpected frame {opcode} during the handshake")
        return json.loads(payload.decode("utf-8"))
