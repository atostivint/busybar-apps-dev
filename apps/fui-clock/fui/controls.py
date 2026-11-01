"""The bar's wheel, read from its state stream (adapted from jam-intro).

/api/status/ws is a WebSocket that, once sent {"enable": true}, pushes protobuf `State` messages: mostly screen
frames, plus an `input` update for every wheel step and button press. Nothing else in the HTTP API reports input.
A background thread keeps the stream open (pinging it, or the bar drops the client after ~10 s) and counts what
comes in. The manager proxies the stream, so --host 127.0.0.1:8321 works. If it is missing the clock just runs
without controls.
"""
import base64
import os
import socket
import struct
import threading
import time


class Controls:
    def __init__(self, host):
        self.host = host.replace("http://", "").rstrip("/")
        self.lock = threading.Lock()
        self.steps = 0     # signed wheel steps since the last take()
        self.clicks = 0    # wheel clicks (the OK button) since then
        threading.Thread(target=self._run, daemon=True).start()

    def take(self):
        """(signed wheel steps, wheel clicks) since the previous call."""
        with self.lock:
            taken = self.steps, self.clicks
            self.steps = self.clicks = 0
        return taken

    def _run(self):
        while True:
            try:
                self._listen()
            except (OSError, EOFError, ValueError, IndexError):
                pass
            time.sleep(2)  # bar unplugged or busy: try again

    def _listen(self):
        name, _, port = self.host.partition(":")
        sock = socket.create_connection((name, int(port or 80)), timeout=5)
        key = base64.b64encode(os.urandom(16)).decode()
        sock.sendall(("GET /api/status/ws HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                      "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n" % (self.host, key)).encode())
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
                send(9, b"fui")
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
        # button_event (1) {button: OK 0 / BACK 1 / START 2, action: PRESS 0} (OK is the wheel's click),
        # encoder_event (3) {delta: sint32}
        for number, update in _fields(state):
            if number != 2:
                continue
            for kind, event in _fields(update):
                if kind != 11:
                    continue
                for which, body in _fields(event):
                    values = dict(_fields(body))
                    with self.lock:
                        if which == 1 and values.get(2, 0) == 0 and values.get(1, 0) == 0:
                            self.clicks += 1
                        elif which == 3:
                            raw = values.get(1, 0)
                            self.steps += (raw >> 1) ^ -(raw & 1)


def _fields(data):
    """(field number, value) pairs of a protobuf message: ints for varints, bytes for everything else."""
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
