"""Tests for haws.py: the event payload, the URL mapping, and the idle keepalive.

Stdlib only, no bar and no Home Assistant: the keepalive test talks to a WebSocket server this
file owns on 127.0.0.1.

    cd apps/notify && python -m unittest -v test_haws
"""
import json
import os
import socket
import struct
import threading
import time
import unittest

import haws


class ParseEvent(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(haws.parse_event({"kind": "livreur", "title": " T ", "message": "m"}),
                         {"kind": "livreur", "title": "T", "message": "m", "source": ""})

    def test_source(self):
        event = haws.parse_event({"kind": "livreur", "source": " TER OUEST ", "title": "t"})
        self.assertEqual(event["source"], "TER OUEST")
        self.assertEqual(haws.parse_event({"source": 3})["source"], "3")  # numeric -> str
        self.assertEqual(haws.parse_event({"source": ["x"]})["source"], "")  # not a scalar

    def test_defaults(self):
        self.assertEqual(haws.parse_event({}),
                         {"kind": "generic", "title": "", "message": "", "source": ""})

    def test_numeric_kind(self):
        self.assertEqual(haws.parse_event({"kind": 3})["kind"], "3")
        self.assertEqual(haws.parse_event({"kind": 1.5})["kind"], "1.5")
        self.assertEqual(haws.parse_event({"kind": True})["kind"], "generic")  # not a number here

    def test_not_an_object(self):
        for payload in (None, [], ["kind"], "kind", 3):
            self.assertIsNone(haws.parse_event(payload))

    def test_non_string_values_are_dropped(self):
        self.assertEqual(haws.parse_event({"title": ["x"], "message": None, "source": {}}),
                         {"kind": "generic", "title": "", "message": "", "source": ""})


class WsUrl(unittest.TestCase):
    def test_bare_host(self):
        self.assertEqual(haws.ws_url("192.168.59.211"), "ws://192.168.59.211/api/websocket")

    def test_http_and_port(self):
        self.assertEqual(haws.ws_url("http://192.168.59.211:80"),
                         "ws://192.168.59.211:80/api/websocket")

    def test_https(self):
        self.assertEqual(haws.ws_url("https://ha.lan"), "wss://ha.lan/api/websocket")

    def test_trailing_slash_and_full_url(self):
        self.assertEqual(haws.ws_url("http://ha.lan/"), "ws://ha.lan/api/websocket")
        self.assertEqual(haws.ws_url("ws://ha.lan/api/websocket"), "ws://ha.lan/api/websocket")

    def test_parts(self):
        self.assertEqual(haws._parts("ws://h:81/api/websocket"), ("h", 81, "/api/websocket", False))
        self.assertEqual(haws._parts("wss://h/api/websocket"), ("h", 443, "/api/websocket", True))


class Config(unittest.TestCase):
    def setUp(self):
        self.saved = {k: os.environ.pop(k, None) for k in ("HA_URL", "HA_TOKEN")}

    def tearDown(self):
        for key, value in self.saved.items():
            os.environ.pop(key, None)
            if value is not None:
                os.environ[key] = value

    def test_none_unless_both_set(self):
        self.assertIsNone(haws.config())
        os.environ["HA_URL"] = "http://h/"
        self.assertIsNone(haws.config())
        os.environ["HA_TOKEN"] = " t "
        self.assertEqual(haws.config(), ("http://h", "t"))

    def test_arguments_win(self):
        os.environ["HA_URL"] = "http://env/"
        os.environ["HA_TOKEN"] = "env"
        self.assertEqual(haws.config("https://arg/", "arg"), ("https://arg", "arg"))


# --- the keepalive: a WebSocket server this file owns ------------------------------------------

def _recv_frame(conn):
    head = conn.recv(2)
    if len(head) < 2:
        return None, None
    opcode, size = head[0] & 0x0F, head[1] & 0x7F
    if size == 126:
        size = struct.unpack(">H", conn.recv(2))[0]
    elif size == 127:
        size = struct.unpack(">Q", conn.recv(8))[0]
    mask = conn.recv(4) if head[1] & 0x80 else b""
    data = b""
    while len(data) < size:
        chunk = conn.recv(size - len(data))
        if not chunk:
            return None, None
        data += chunk
    if mask:
        data = bytes(c ^ mask[i % 4] for i, c in enumerate(data))
    return opcode, data


def _send_frame(conn, opcode, data):
    if len(data) < 126:
        head = bytes([0x80 | opcode, len(data)])
    else:
        head = bytes([0x80 | opcode, 126]) + struct.pack(">H", len(data))
    conn.sendall(head + data)


class FakeHA:
    """Accepts WebSocket clients, completes the HA handshake, then records what they send."""

    def __init__(self):
        self.srv = socket.socket()
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(2)
        self.srv.settimeout(0.05)
        self.port = self.srv.getsockname()[1]
        self.received = []  # (opcode, payload) from the client
        self.accepts = 0
        self.subscribed = threading.Event()
        self.done = False
        threading.Thread(target=self._accept, daemon=True).start()

    def close(self):
        self.done = True
        try:
            self.srv.close()
        except OSError:
            pass

    def wait_for(self, opcode, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for op, _ in list(self.received):
                if op == opcode:
                    return True
            time.sleep(0.02)
        return False

    def _accept(self):
        while not self.done:
            try:
                conn, _ = self.srv.accept()
            except OSError:  # timeout, or the socket was closed by close()
                continue
            self.accepts += 1
            if self.accepts > 1:  # a reconnect: count it, never serve it
                conn.close()
                continue
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn):
        try:
            request = b""
            while b"\r\n\r\n" not in request:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                request += chunk
            conn.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                         b"Connection: Upgrade\r\n\r\n")
            _send_frame(conn, 1, json.dumps({"type": "auth_required"}).encode())
            self.received.append(_recv_frame(conn))
            _send_frame(conn, 1, json.dumps({"type": "auth_ok"}).encode())
            self.received.append(_recv_frame(conn))
            _send_frame(conn, 1, json.dumps({"id": 1, "type": "result", "success": True,
                                            "result": None}).encode())
            self.subscribed.set()
            conn.settimeout(0.2)
            while not self.done:
                try:
                    opcode, data = _recv_frame(conn)
                except (socket.timeout, TimeoutError):
                    continue
                if opcode is None:
                    break
                self.received.append((opcode, data))
                if opcode == 9:  # answer the ping, like HA does
                    _send_frame(conn, 10, data)
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass


class Keepalive(unittest.TestCase):
    """Fix 1: an idle socket is pinged, it is not torn down and reconnected."""

    def test_idle_socket_is_pinged_and_not_reconnected(self):
        saved = haws.PING_S
        haws.PING_S = 0.2  # the real 20 s would make the test unusable
        server = FakeHA()
        ws = None
        try:
            ws = haws.HAWebSocket(lambda data: None, f"http://127.0.0.1:{server.port}", "token")
            ws.start()
            self.assertTrue(server.subscribed.wait(5), "the client never authenticated and subscribed")
            self.assertTrue(server.wait_for(9, 5),
                            "no opcode-9 ping after an idle period: the keepalive is dead code "
                            f"(frames received: {[(op, d[:40]) for op, d in server.received]})")
            ws.stop()
            time.sleep(0.2)  # a reconnect, if any, has had time to be accepted by now
            self.assertEqual(server.accepts, 1, "the client reconnected instead of pinging")
        finally:
            if ws is not None:
                ws.stop()
            server.close()
            haws.PING_S = saved


if __name__ == "__main__":
    unittest.main()
