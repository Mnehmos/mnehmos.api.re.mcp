"""Loopback passthrough proxy: real HTTP through a real socket, captured.

A stdlib HTTP server is the origin; http.client points at the proxy in
absolute-form (what a proxy-configured app does). The assertions cover the
things that matter: the exchange works end to end, both sides are recorded,
credentials never persist, CONNECT is refused (not tunneled), chunked bodies
relay intact, and an unreachable origin yields 502 rather than a hang.
"""

import http.client
import http.server
import json
import socket
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from apire.capture.http_proxy import HttpProxyListener
from apire.store import Store

AUTH = "fixture: synthetic local origin, authorized"
SECRET = "Bearer " + "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJmaXh0dXJlIn0.c2ln"


class _Origin(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence
        pass

    def _json(self, status: int, payload: dict):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/items"):
            self._json(200, {"items": [{"id": 1, "name": "kick"}], "total": 1})
        elif self.path.startswith("/api/auth"):
            saw = "authorization" in {k.lower() for k in self.headers.keys()}
            self._json(200, {"authenticated": saw})
        else:
            self._json(404, {"error": "nope"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self._json(201, {"created": True, "bytes": len(body)})


@pytest.fixture()
def rig(tmp_path):
    origin = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Origin)
    threading.Thread(target=origin.serve_forever, daemon=True).start()
    store = Store(root=tmp_path)
    cap = store.start_capture(transport="http_proxy", authorization_statement=AUTH)
    listener = HttpProxyListener()
    info = listener.start(store, cap["capture_id"], host="127.0.0.1", port=0)
    # port 0 -> OS chose; discover the real bound port
    proxy_port = listener._sock.getsockname()[1]
    yield store, cap["capture_id"], listener, origin.server_port, proxy_port
    listener.stop()
    origin.shutdown()


def _request(proxy_port: int, method: str, url: str, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", proxy_port, timeout=10)
    conn.request(method, url, body=body, headers=headers or {})
    resp = conn.getresponse()
    data = resp.read()
    status = resp.status
    conn.close()
    return status, data


def test_exchange_is_relayed_and_recorded_both_sides(rig):
    store, cap_id, listener, origin_port, proxy_port = rig
    status, data = _request(proxy_port, "GET", f"http://127.0.0.1:{origin_port}/api/items?page=2")
    assert status == 200
    assert json.loads(data)["items"][0]["name"] == "kick"

    frames = store.frames(cap_id)
    kinds = [f["kind_hint"] for f in frames]
    assert kinds == ["http_request", "http_response"]
    req, resp = frames
    assert req["payload"]["method"] == "GET"
    assert req["payload"]["url"].endswith("/api/items?page=2")
    assert resp["payload"]["status"] == 200
    assert "kick" in resp["payload"]["body_sample"], "response body sample feeds schema induction"


def test_credentials_never_reach_the_manifest(rig):
    store, cap_id, listener, origin_port, proxy_port = rig
    status, data = _request(
        proxy_port, "GET", f"http://127.0.0.1:{origin_port}/api/auth", headers={"Authorization": SECRET}
    )
    assert json.loads(data)["authenticated"] is True, "the origin must still receive auth (passthrough)"
    manifest = (Path(store.captures_dir) / cap_id / "manifest.jsonl").read_text(encoding="utf-8")
    assert SECRET not in manifest
    assert "eyJhbGciOiJIUzI1NiJ9" not in manifest


def test_post_body_round_trips(rig):
    store, cap_id, listener, origin_port, proxy_port = rig
    status, data = _request(
        proxy_port, "POST", f"http://127.0.0.1:{origin_port}/api/items", body='{"name":"snare"}', headers={"Content-Type": "application/json"}
    )
    assert status == 201
    assert json.loads(data)["bytes"] == len('{"name":"snare"}')
    frames = store.frames(cap_id)
    assert frames[0]["payload"]["postData"] == '{"name":"snare"}'


def test_connect_is_refused_and_recorded(rig):
    store, cap_id, listener, origin_port, proxy_port = rig
    status, data = _request(proxy_port, "CONNECT", "example.com:443")
    assert status == 501
    assert b"refused" in data.lower()
    frames = store.frames(cap_id)
    assert any(f["payload"].get("method") == "CONNECT" and f["payload"].get("refused") for f in frames)


def test_unreachable_origin_yields_502(rig):
    store, cap_id, listener, origin_port, proxy_port = rig
    # port 1 is reliably closed
    status, data = _request(proxy_port, "GET", "http://127.0.0.1:1/api/items")
    assert status == 502
    frames = store.frames(cap_id)
    assert any(f["payload"].get("status") == 502 for f in frames), "the failed exchange is still recorded"


def test_chunked_response_relays_intact(tmp_path):
    """A raw origin that answers chunked; the client must receive the same
    body, and the sample must be dechunked for shape induction."""
    raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    raw.bind(("127.0.0.1", 0))
    raw.listen(1)
    origin_port = raw.getsockname()[1]

    def serve():
        conn, _ = raw.accept()
        conn.recv(65536)
        conn.sendall(
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nTransfer-Encoding: chunked\r\n\r\n"
            b"7\r\n{\"a\": 1\r\n"
            b"9\r\n, \"b\": 2}\r\n"
            b"0\r\n\r\n"
        )
        conn.close()
        raw.close()

    threading.Thread(target=serve, daemon=True).start()
    store = Store(root=tmp_path)
    cap = store.start_capture(transport="http_proxy", authorization_statement=AUTH)
    listener = HttpProxyListener()
    listener.start(store, cap["capture_id"], port=0)
    proxy_port = listener._sock.getsockname()[1]
    try:
        status, data = _request(proxy_port, "GET", f"http://127.0.0.1:{origin_port}/chunked")
        assert status == 200
        assert json.loads(data) == {"a": 1, "b": 2}
        frames = store.frames(cap["capture_id"])
        sample = frames[1]["payload"]["body_sample"]
        assert json.loads(sample) == {"a": 1, "b": 2}, "sample must be dechunked"
    finally:
        listener.stop()
