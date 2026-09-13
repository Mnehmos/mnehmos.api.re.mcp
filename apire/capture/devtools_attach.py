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

import base64
import json
import os
import socket
import threading

import websocket  # websocket-client, pinned in requirements.txt

from ..errors import TransportError

_STATIC_EXTS = (".js", ".mjs", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2", ".ttf", ".map", ".wasm")
_MAX_WS_PAYLOAD = 4000
_MAX_POST_DATA = 2000
_MAX_RESPONSE_BODY = 16384
# Fetch cap raised from 2 MB to 8 MB (env-overridable): the largest Next.js
# catalog files were being skipped, and they are exactly the schema source.
_MAX_BODY_FETCH = int(os.environ.get("APIRE_MAX_BODY_FETCH", "8000000"))


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
    if method == "Network.webSocketCreated":
        url = str(params.get("url", "")).split("?", 1)[0]
        if not url:
            return []
        return [
            {
                "kind_hint": "ws_frame",
                "transport": "devtools_attach",
                "direction": "unspecified",
                "channel": channel,
                "payload": {"event": "open", "ws_url": url},
            }
        ]
    if method == "Network.webSocketClosed":
        return [
            {
                "kind_hint": "ws_frame",
                "transport": "devtools_attach",
                "direction": "unspecified",
                "channel": channel,
                "payload": {"event": "closed"},
            }
        ]
    if method == "Network.webSocketHandshakeResponseReceived":
        resp = params.get("response", {}) or {}
        return [
            {
                "kind_hint": "ws_frame",
                "transport": "devtools_attach",
                "direction": "server_to_client",
                "channel": channel,
                "payload": {
                    "event": "handshake",
                    "status": resp.get("status", 0),
                    "headers": resp.get("headers", {}),
                },
            }
        ]
    return []


def _body_fetchable(headers: dict, limit: int = _MAX_BODY_FETCH) -> bool:
    """Fetch a response body only if it can plausibly be small. Absent
    content-length: attempt (chunked/streamed bodies are exactly what we
    want to see), over the limit: skip and record the skip."""
    for name, value in (headers or {}).items():
        if str(name).lower() == "content-length":
            try:
                return int(value) <= limit
            except (TypeError, ValueError):
                return True
    return True


class DevtoolsAttachListener:
    transport = "devtools_attach"
    # v2 adds opt-in response bodies (Network.getResponseBody, size-capped)
    # and WebSocket lifecycle events (open/closed/handshake). v1 captures
    # carried neither — the correlator's instrument guard will flag any
    # comparison that mixes the two.
    version = 2

    def __init__(self):
        self._ws: websocket.WebSocket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._bodies = False
        self._stats = {
            "frames": 0,
            "events": 0,
            "dropped": 0,
            "errors": [],
            "target": "",
            "bodies_skipped": 0,
            "bodies_pending_at_stop": 0,
        }

    def start(
        self,
        store,
        capture_id: str,
        host: str = "127.0.0.1",
        port: int = 9222,
        path: str = "",
        wait_seconds: int = 10,
        bodies: bool = False,
        **_,
    ) -> dict:
        if self._ws:
            raise TransportError("listener already attached")
        self._bodies = bool(bodies)
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
        # Body retrieval requires Chromium's resource buffer, so buffering is
        # enabled only when bodies were requested.
        if self._bodies:
            enable_params = {"maxTotalBufferSize": 50_000_000, "maxResourceBufferSize": 5_000_000}
        else:
            enable_params = {"maxTotalBufferSize": 0, "maxResourceBufferSize": 0}
        ws.send(json.dumps({"id": 1, "method": "Network.enable", "params": enable_params}))
        channel = target.get("url", "")

        def loop():
            pending: list[dict] = []
            ws_urls: dict[str, str] = {}
            pending_responses: dict[str, dict] = {}  # requestId -> stashed response frame
            in_flight: dict[int, dict] = {}  # command id -> frame awaiting its body
            body_requests: dict[int, str] = {}  # command id -> requestId
            cmd_seq = 1

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
                method = message.get("method")

                # reply to a getResponseBody command: complete the in-flight
                # frame. (The first implementation looked the frame up in the
                # stash it had already popped — every fetched body was
                # silently dropped. Two maps exist so that cannot recur.)
                if "id" in message and message["id"] in body_requests:
                    cmd_id = message["id"]
                    body_requests.pop(cmd_id)
                    frame = in_flight.pop(cmd_id, None)
                    if frame is not None:
                        result = message.get("result") or {}
                        body = result.get("body") or ""
                        if result.get("base64Encoded"):
                            try:
                                body = base64.b64decode(body).decode("utf-8", errors="replace")
                            except (ValueError, TypeError):
                                body = ""
                        frame["payload"]["body_sample"] = body[:_MAX_RESPONSE_BODY]
                        frame["payload"]["body_truncated"] = len(body) > _MAX_RESPONSE_BODY
                        pending.append(frame)
                    continue

                if method == "Network.webSocketCreated":
                    wparams = message.get("params") or {}
                    if wparams.get("requestId") and wparams.get("url"):
                        ws_urls[wparams["requestId"]] = str(wparams["url"]).split("?", 1)[0]

                if method == "Network.responseReceived" and self._bodies:
                    params = message.get("params") or {}
                    frames = cdp_event_to_frames(message, channel)
                    if frames:
                        pending_responses[params.get("requestId", "")] = frames[0]
                else:
                    frames = cdp_event_to_frames(message, channel)
                    rid = (message.get("params") or {}).get("requestId")
                    if rid in ws_urls:
                        for f in frames:
                            if f["kind_hint"] == "ws_frame":
                                f["payload"].setdefault("ws_url", ws_urls[rid])
                    pending.extend(frames)

                if method in ("Network.loadingFinished", "Network.loadingFailed"):
                    params = message.get("params") or {}
                    rid = params.get("requestId")
                    frame = pending_responses.pop(rid, None) if self._bodies else None
                    if frame is not None:
                        if method == "Network.loadingFinished" and _body_fetchable(frame["payload"].get("headers", {})):
                            cmd_seq += 1
                            in_flight[cmd_seq] = frame
                            body_requests[cmd_seq] = rid
                            ws.send(
                                json.dumps({"id": cmd_seq, "method": "Network.getResponseBody", "params": {"requestId": rid}})
                            )
                        else:
                            self._stats["bodies_skipped"] += 1
                            pending.append(frame)

                if len(pending) >= 25:
                    store.append_frames(capture_id, pending)
                    self._stats["frames"] += len(pending)
                    pending = []

            # stop: flush stashed/in-flight responses without bodies (never
            # drop evidence silently — the counts are reported)
            self._stats["bodies_pending_at_stop"] = len(pending_responses) + len(in_flight)
            pending.extend(pending_responses.values())
            pending.extend(in_flight.values())
            if pending:
                try:
                    store.append_frames(capture_id, pending)
                    self._stats["frames"] += len(pending)
                except Exception as exc:  # capture may have been stopped first
                    self._stats["errors"].append(f"flush: {type(exc).__name__}: {exc}")

        self._thread = threading.Thread(target=loop, daemon=True, name=f"devtools_attach:{port}")
        self._thread.start()
        return {"attached": target.get("url", ""), "title": target.get("title", ""), "status": "observing", "bodies": self._bodies}

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
