"""DevTools attach: event mapping, the raw /json/list client, and (when a
real endpoint exists) a live attach. The live test skips on machines without
a designated debug port — CI must not depend on FL Studio running.
"""

import json
import socket
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from apire.capture import devtools_attach as dt

CDP_AVAILABLE = False
try:
    targets = dt._http_get_json("127.0.0.1", 9222, "/json/list", timeout=1.0)
    CDP_AVAILABLE = any(t.get("type") == "page" for t in targets)
except Exception:
    CDP_AVAILABLE = False


def test_request_event_maps_to_http_request_and_skips_static():
    msg = {
        "method": "Network.requestWillBeSent",
        "params": {
            "request": {
                "method": "POST",
                "url": "https://sounds.cloud.image-line.com/api/v1/search?q=kick&token=abc",
                "headers": {"Authorization": "Bearer xyz", "Content-Type": "application/json"},
                "postData": '{"query":"kick"}',
            }
        },
    }
    frames = dt.cdp_event_to_frames(msg, "fl-cloud")
    assert len(frames) == 1
    f = frames[0]
    assert f["kind_hint"] == "http_request"
    assert f["payload"]["method"] == "POST"
    assert f["transport"] == "devtools_attach"
    # static assets are skipped
    static = {"method": "Network.requestWillBeSent", "params": {"request": {"url": "https://x/y/app.js"}}}
    assert dt.cdp_event_to_frames(static) == []


def test_response_event_maps_with_status_and_path():
    msg = {
        "method": "Network.responseReceived",
        "params": {
            "response": {
                "url": "https://sounds.cloud.image-line.com/api/v1/search?q=kick",
                "status": 200,
                "mimeType": "application/json",
                "headers": {"content-type": "application/json"},
            }
        },
    }
    frames = dt.cdp_event_to_frames(msg, "fl-cloud")
    assert len(frames) == 1
    p = frames[0]["payload"]
    assert p["path"] == "/api/v1/search"
    assert p["status"] == 200


def test_ws_frame_events_carry_direction_and_truncate():
    big = "x" * 9000
    recv = {"method": "Network.webSocketFrameReceived", "params": {"response": {"opcode": 1, "payloadData": big}}}
    sent = {"method": "Network.webSocketFrameSent", "params": {"response": {"opcode": 1, "payloadData": "hi"}}}
    r = dt.cdp_event_to_frames(recv)[0]
    s = dt.cdp_event_to_frames(sent)[0]
    assert r["direction"] == "server_to_client" and r["payload"]["truncated"] is True
    assert len(r["payload"]["payloadData"]) == 4000
    assert s["direction"] == "client_to_server"


def test_unknown_events_are_ignored_not_guessed():
    assert dt.cdp_event_to_frames({"method": "Network.loadingFinished", "params": {}}) == []
    assert dt.cdp_event_to_frames({}) == []


def test_http_get_json_against_local_socket_server():
    """Exercises the raw socket GET (urllib.request is banned) without CDP."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def serve():
        conn, _ = server.accept()
        conn.recv(4096)
        body = json.dumps([{"type": "page", "url": "http://test/"}]).encode()
        conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
        conn.close()
        server.close()

    threading.Thread(target=serve, daemon=True).start()
    got = dt._http_get_json("127.0.0.1", port, "/json/list")
    assert got == [{"type": "page", "url": "http://test/"}]


def test_missing_endpoint_is_a_typed_error():
    with pytest.raises(Exception) as err:
        dt._http_get_json("127.0.0.1", 59999, "/json/list", timeout=1.0)
    assert "devtools endpoint" in str(err.value)


@pytest.mark.skipif(not CDP_AVAILABLE, reason="no WebView2/CDP endpoint on 127.0.0.1:9222")
def test_live_attach_observes_events(tmp_path):
    """Live dogfood: attach to the real target, confirm the pipeline emits
    frames. Skips cleanly when no debug port is designated."""
    from apire.store import Store

    store = Store(root=tmp_path)
    auth = "live test: designated debug channel"
    cap = store.start_capture(transport="devtools_attach", authorization_statement=auth)
    listener = dt.DevtoolsAttachListener()
    info = listener.start(store, cap["capture_id"], wait_seconds=3)
    assert info["status"] == "observing"
    import time

    time.sleep(6)
    stats = listener.stop()
    store.stop_capture(cap["capture_id"])
    frames = store.frames(cap["capture_id"])
    # Idle pages may emit few events; the assertion is on the mechanism:
    # attach succeeded and stats are coherent.
    assert stats["target"]
    assert stats["frames"] == len(frames)
