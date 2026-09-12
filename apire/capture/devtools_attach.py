"""DevTools-protocol attach transport (ADR-003, attach mode).

Attaches to a debugging channel the operator has designated — for FL Studio,
the WebView2 remote-debugging port enabled at launch via
`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=<port>`. It
observes what the embedded browser does (network events, WebSocket frames)
and never drives the page, never injects script, never originates an
application request. The only messages sent on the channel are CDP control
commands (`Network.enable`), which are debugger instructions, not app
traffic.

This module lives in apire/capture/, the only package permitted to touch
sockets; the /json/list fetch is a raw socket GET because urllib.request is
on the engine ban list (tests/test_no_egress.py) and that ban is not to be
weakened for convenience.
"""

from __future__ import annotations

import json
import socket
import threading

import websocket  # websocket-client, pinned in requirements.txt

from ..errors import TransportError

_STATIC_EXTS = (".js", ".mjs", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2", ".ttf", ".map", ".wasm")
_MAX_WS_PAYLOAD = 4000
_MAX_POST_DATA = 2000


def _is_static(url: str) -> bool:
    path = url.split("?", 1)[0].lower()
    return path.endswith(_STATIC_EXTS)


def _http_get_json(host: str, port: int, path: str, timeout: float = 5.0) -> object:
    """Minimal HTTP/1.1 GET for the debugger's HTTP endpoints.

    Chromium keeps debugger connections alive, so this honors Content-Length
    and chunked transfer encoding rather than reading to EOF (a live test
    caught the read-to-EOF version hanging on a perfectly healthy endpoint).
    """
    try:
        conn = socket.create_connection((host, port), timeout=timeout)
    except OSError as exc:
        raise TransportError(
            f"cannot reach devtools endpoint {host}:{port}: {exc}",
            hint="relaunch the target with its remote-debugging port enabled (for WebView2: WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS)",
        ) from exc
    conn.settimeout(timeout)
    try:
        req = f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nConnection: close\r\n\r\n"
        conn.sendall(req.encode("ascii"))
        buf = b""
        while b"\r\n\r\n" not in buf:
            block = conn.recv(65536)
            if not block:
                break
            buf += block
            if len(buf) > 1_000_000:
                break
        head, _, rest = buf.partition(b"\r\n\r\n")
        headers = {}
        for line in head.split(b"\r\n")[1:]:
            name, _, value = line.partition(b":")
            headers[name.strip().lower()] = value.strip().lower()
        body = rest
        if headers.get(b"transfer-encoding", b"").startswith(b"chunked"):
            body = _read_chunked(conn, rest, timeout)
        elif b"content-length" in headers:
            need = int(headers[b"content-length"])
            while len(body) < need:
                block = conn.recv(min(65536, need - len(body)))
                if not block:
                    break
                body += block
    finally:
        conn.close()
    text = body.decode("utf-8", errors="replace")
    start = min((i for i in (text.find("["), text.find("{")) if i >= 0), default=-1)
    if start < 0:
        raise TransportError("devtools endpoint returned no JSON", body_head=text[:200])
    return json.loads(text[start:])


def _read_chunked(conn: socket.socket, initial: bytes, timeout: float) -> bytes:
    """Decode chunked transfer encoding incrementally."""
    buf = initial
    out = b""
    deadline_reads = 0
    while True:
        while b"\r\n" not in buf:
            block = _recv_or_empty(conn, timeout)
            if not block:
                return out
            buf += block
            deadline_reads += 1
            if deadline_reads > 10000:
                return out
        size_line, _, buf = buf.partition(b"\r\n")
        try:
            size = int(size_line.split(b";")[0], 16)
        except ValueError:
            return out
        if size == 0:
            return out
        while len(buf) < size + 2:
            block = _recv_or_empty(conn, timeout)
            if not block:
                return out
            buf += block
        out += buf[:size]
        buf = buf[size + 2 :]


def _recv_or_empty(conn: socket.socket, timeout: float) -> bytes:
    try:
        return conn.recv(65536)
    except (socket.timeout, OSError):
        return b""


def cdp_event_to_frames(message: dict, channel: str = "") -> list[dict]:
    """Pure mapping: one CDP event -> zero or more frames. Static assets are
    skipped by default — the API surface is what we are after, not the
    bundle. Response bodies are not fetched (v1): headers and frames only."""
    method = message.get("method")
    params = message.get("params") or {}
    if method == "Network.requestWillBeSent":
        req = params.get("request", {})
        url = str(req.get("url", ""))
        if not url or _is_static(url):
            return []
        post = req.get("postData") or ""
        return [
            {
                "kind_hint": "http_request",
                "transport": "devtools_attach",
                "direction": "client_to_server",
                "channel": channel,
                "payload": {
                    "method": req.get("method", "GET"),
                    "url": url,
                    "headers": req.get("headers", {}),
                    "postData": post[:_MAX_POST_DATA],
                    "postData_truncated": len(post) > _MAX_POST_DATA,
                },
            }
        ]
    if method == "Network.responseReceived":
        resp = params.get("response", {})
        url = str(resp.get("url", ""))
        if not url or _is_static(url):
            return []
        path = url.split("?", 1)[0]
        tail = path.split("//", 1)[-1]
        path = "/" + tail.split("/", 1)[-1] if "/" in tail else "/"
        return [
            {
                "kind_hint": "http_response",
                "transport": "devtools_attach",
                "direction": "server_to_client",
                "channel": channel,
                "payload": {
                    "path": path,
                    "url": url,
                    "status": resp.get("status", 0),
                    "mimeType": resp.get("mimeType", ""),
                    "headers": resp.get("headers", {}),
                },
            }
        ]
    if method in ("Network.webSocketFrameReceived", "Network.webSocketFrameSent"):
        frame = params.get("response", {})
        payload_data = str(frame.get("payloadData", ""))
        return [
            {
                "kind_hint": "ws_frame",
                "transport": "devtools_attach",
                "direction": "server_to_client" if method.endswith("Received") else "client_to_server",
                "channel": channel,
                "payload": {
                    "opcode": frame.get("opcode"),
                    "payloadData": payload_data[:_MAX_WS_PAYLOAD],
                    "truncated": len(payload_data) > _MAX_WS_PAYLOAD,
                },
            }
        ]
    return []


class DevtoolsAttachListener:
    transport = "devtools_attach"
    version = 1

    def __init__(self):
        self._ws: websocket.WebSocket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._stats = {"frames": 0, "events": 0, "dropped": 0, "errors": [], "target": ""}

    def start(self, store, capture_id: str, host: str = "127.0.0.1", port: int = 9222, path: str = "", wait_seconds: int = 10, **_) -> dict:
        if self._ws:
            raise TransportError("listener already attached")
        target = self._wait_for_target(host, port, path, wait_seconds)
        self._stats["target"] = f"{target.get('title', '')} | {target.get('url', '')}"
        try:
            # suppress_origin: Chromium rejects DevTools WS handshakes that
            # carry an Origin header (403), so the client must not send one.
            ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=5, suppress_origin=True)
            ws.settimeout(1.0)
        except Exception as exc:
            raise TransportError(f"cannot attach to {target['webSocketDebuggerUrl']}: {exc}") from exc
        self._ws = ws
        self._stop.clear()
        # Enable network observation. This is the only client->browser message
        # the transport sends: a debugger control command, not app traffic.
        ws.send(json.dumps({"id": 1, "method": "Network.enable", "params": {"maxTotalBufferSize": 0, "maxResourceBufferSize": 0}}))
        channel = target.get("url", "")

        def loop():
            pending: list[dict] = []
            ws_urls: dict[str, str] = {}
            while not self._stop.is_set():
                try:
                    raw = ws.recv()
                except websocket.WebSocketTimeoutException:
                    if pending:
                        store.append_frames(capture_id, pending)
                        self._stats["frames"] += len(pending)
                        pending = []
                    continue
                except (websocket.WebSocketConnectionClosedException, OSError) as exc:
                    # The observed app closed the channel (crash, restart,
                    # navigation). Never silent: it is a warning on the capture.
                    self._stats["errors"].append(f"channel closed: {type(exc).__name__}")
                    break
                if not raw:
                    continue
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                self._stats["events"] += 1
                if message.get("method") == "Network.webSocketCreated":
                    params = message.get("params") or {}
                    if params.get("requestId") and params.get("url"):
                        ws_urls[params["requestId"]] = str(params["url"]).split("?", 1)[0]
                frames = cdp_event_to_frames(message, channel)
                rid = (message.get("params") or {}).get("requestId")
                if rid in ws_urls:
                    for f in frames:
                        if f["kind_hint"] == "ws_frame":
                            f["payload"]["ws_url"] = ws_urls[rid]
                pending.extend(frames)
                if len(pending) >= 25:
                    store.append_frames(capture_id, pending)
                    self._stats["frames"] += len(pending)
                    pending = []
            if pending:
                try:
                    store.append_frames(capture_id, pending)
                    self._stats["frames"] += len(pending)
                except Exception as exc:  # capture may have been stopped first
                    self._stats["errors"].append(f"flush: {type(exc).__name__}: {exc}")

        self._thread = threading.Thread(target=loop, daemon=True, name=f"devtools_attach:{port}")
        self._thread.start()
        return {"attached": target.get("url", ""), "title": target.get("title", ""), "status": "observing"}

    def _wait_for_target(self, host: str, port: int, path_filter: str, wait_seconds: int) -> dict:
        import time

        deadline = time.time() + max(0, wait_seconds)
        last_error: Exception | None = None
        while True:
            try:
                targets = _http_get_json(host, port, "/json/list")
                pages = [t for t in targets if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
                if path_filter:
                    pages = [t for t in pages if path_filter in t.get("url", "")] or pages
                if pages:
                    return pages[0]
            except (TransportError, json.JSONDecodeError) as exc:
                last_error = exc
            if time.time() >= deadline:
                raise TransportError(
                    f"no page target found on {host}:{port} within {wait_seconds}s",
                    hint="is the remote-debugging port enabled on the target at launch?",
                    last_error=str(last_error) if last_error else "",
                )
            # Tight poll: a page target exists before navigation completes, and
            # attaching late means missing the load-time API calls entirely.
            time.sleep(0.25)

    def stop(self) -> dict:
        self._stop.set()
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
        return dict(self._stats)

    def status(self) -> dict:
        return {**self._stats, "listening": self._ws is not None}
