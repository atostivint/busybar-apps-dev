"""The bar's buttons (snooze), read from its state stream.

/api/status/ws is a WebSocket that, once sent {"enable": true}, pushes protobuf `State` messages;
button presses arrive as State.updates (2) -> StateUpdate.input (11) -> InputEvent.button_event (1)
{button: OK 0 / BACK 1 / START 2, action: PRESS 0}. A background thread keeps the stream open
(pinging it, or the bar drops the client after ~10 s) and counts the presses of one button. If the
stream is missing the app simply runs without a snooze button. Same approach as jam-intro.
"""
import base64
import os
import socket
import struct
import threading
import time
import urllib.parse

import rt

BUTTONS = {"ok": 0, "back": 1, "start": 2}


class Buttons:
    def __init__(self, host, button="start", token=None):
        self.host = host.replace("http://", "").rstrip("/")
        self.button = BUTTONS[button]
        self.token = token
        self.lock = threading.Lock()
        self.count = 0
        threading.Thread(target=self._run, daemon=True).start()

    def pressed(self):
        """Presses of the snooze button since the previous call."""
        with self.lock:
            n, self.count = self.count, 0
        return n

    def _run(self):
        while True:
            try:
                self._listen()
            except (OSError, EOFError, ValueError, IndexError):
                pass
            time.sleep(2)  # bar busy or unplugged: try again

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
            size = bytes([0x80 | len(data)]) if len(data) < 126 else bytes([0xFE]) + struct.pack(">H", len(data))
            sock.sendall(bytes([0x80 | opcode]) + size + mask + bytes(c ^ mask[i % 4] for i, c in enumerate(data)))

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
                send(9, b"ter")
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
        for number, update in rt._fields(state):
            if number != 2 or not isinstance(update, bytes):
                continue
            for kind, event in rt._fields(update):
                if kind != 11 or not isinstance(event, bytes):
                    continue
                for which, body in rt._fields(event):
                    if which != 1 or not isinstance(body, bytes):
                        continue
                    values = dict(rt._fields(body))
                    if values.get(2, 0) == 0 and values.get(1, 0) == self.button:  # a press of our button
                        with self.lock:
                            self.count += 1
