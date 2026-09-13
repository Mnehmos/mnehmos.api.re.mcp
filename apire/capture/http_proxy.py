"""Loopback passthrough HTTP proxy (ADR-003, listen mode).

The application under observation points its HTTP proxy setting at this
listener. The proxy forwards **exactly what the client sent** — it never
originates a request of its own — relays the origin's response back, and
records both as frames. This is the sanctioned passthrough path from
docs/security-model.md: the responses a client receives are the origin's,
and the requests that leave are the client's.

CONNECT (TLS tunneling) is refused with 501 and recorded: an opaque tunnel
is unobservable, and pretending otherwise would violate "observe or refuse".

v1 scope, stated rather than implied: one exchange per connection
(`Connection: close` is enforced hop-by-hop both directions); the upstream
is the absolute-form request target; response bodies are sampled (2 KiB)
for shape induction; chunked bodies are decoded for the sample while the
raw chunked stream is relayed verbatim.

All I/O goes through `_Reader`, which owns the read buffer — header reads
must never swallow body bytes (a live defect the tests caught the first
time this was written with naked recv calls).
"""

from __future__ import annotations

import socket
import threading
from urllib.parse import urlsplit  # parsing only; no network use

from ..errors import TransportError

_MAX_BODY_SAMPLE = 2000
_MAX_SSE_EVENTS = 500
_SSE_READ_TIMEOUT = 2.0
_HOP_BY_HOP = {"connection", "proxy-connection", "keep-alive", "te", "trailer", "upgrade"}
_READ_TIMEOUT = 30.0


def _parse_sse_event(block: str) -> dict | None:
    """Parse one SSE event block (the text between blank lines)."""
    fields: dict[str, str] = {}
    data_lines: list[str] = []
    for line in block.splitlines():
        if not line or line.startswith(":"):
            continue
        name, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        if name == "data":
            data_lines.append(value)
        elif name in ("event", "id", "retry"):
            fields[name] = value
    if not data_lines and not fields:
        return None
    event = {**fields}
    if data_lines:
        event["data"] = "\n".join(data_lines)[:_MAX_BODY_SAMPLE]
    return event


class _Reader:
    """Buffered reader over a socket; the buffer survives between reads, so
    head-then-body reads cannot lose or double-count bytes."""

    def __init__(self, conn: socket.socket, initial: bytes = b""):
        self.conn = conn
        self.buf = bytearray(initial)

    def _fill(self, n: int = 65536) -> bool:
        block = self.conn.recv(n)
        if not block:
            return False
        self.buf += block
        return True

    def read_until(self, marker: bytes, limit: int = 262144) -> tuple[bytes, bool]:
        while True:
            idx = self.buf.find(marker)
            if idx >= 0:
                end = idx + len(marker)
                out = bytes(self.buf[:end])
                del self.buf[:end]
                return out, True
            if len(self.buf) > limit:
                raise TransportError("header block exceeded limit")
            if not self._fill():
                out = bytes(self.buf)
                self.buf.clear()
                return out, False

    def read_exact(self, n: int) -> bytes:
        while len(self.buf) < n:
            if not self._fill():
                break
        out = bytes(self.buf[:n])
        del self.buf[: len(out)]
        return out

    def read_line(self, limit: int = 65536) -> bytes:
        line, _ = self.read_until(b"\n", limit)
        return line

    def read_all(self) -> bytes:
        while self._fill():
            pass
        out = bytes(self.buf)
        self.buf.clear()
        return out

    def read_some(self) -> bytes:
        """Buffered bytes if any, else one socket read (caller handles
        socket.timeout). Streaming relays MUST go through this: header
        parsing may already have swallowed early body bytes."""
        if self.buf:
            out = bytes(self.buf)
            self.buf.clear()
            return out
        return self.conn.recv(65536)

    def drain(self) -> bytes:
        out = bytes(self.buf)
        self.buf.clear()
        return out


def _split_head(head: bytes) -> tuple[str, list[tuple[str, str]]]:
    lines = head.rstrip(b"\r\n").split(b"\r\n")
    start_line = lines[0].decode("latin-1")
    headers = []
    for line in lines[1:]:
        if not line:
            continue
        name, _, value = line.partition(b":")
        headers.append((name.decode("latin-1").strip(), value.decode("latin-1").strip()))
    return start_line, headers


def _header(headers: list[tuple[str, str]], name: str) -> str:
    for k, v in headers:
        if k.lower() == name.lower():
            return v
    return ""


def _read_chunked_raw(reader: _Reader, sample_limit: int) -> tuple[bytes, bytes]:
    """Read a chunked stream: (raw bytes for relay, decoded sample)."""
    raw = b""
    decoded = b""
    while True:
        line = reader.read_line()
        if not line:
            return raw, decoded
        raw += line
        try:
            size = int(line.strip().split(b";")[0], 16)
        except ValueError:
            return raw, decoded
        if size == 0:
            while True:
                trailer = reader.read_line()
                if not trailer:
                    break
                raw += trailer
                if trailer in (b"\r\n", b"\n"):
                    break
            return raw, decoded
        chunk = reader.read_exact(size + 2)
        raw += chunk
        decoded += chunk[:size]
        if len(decoded) >= sample_limit:
            decoded = decoded[:sample_limit]


def _read_body(reader: _Reader, headers: list[tuple[str, str]], to_eof: bool) -> tuple[bytes, str]:
    """Read a message body per its framing: (raw_bytes, decoded_sample)."""
    te = _header(headers, "Transfer-Encoding").lower()
    if "chunked" in te:
        raw, decoded = _read_chunked_raw(reader, _MAX_BODY_SAMPLE)
        return raw, decoded.decode("utf-8", errors="replace")
    cl = _header(headers, "Content-Length")
    if cl.isdigit():
        raw = reader.read_exact(int(cl))
        return raw, raw[:_MAX_BODY_SAMPLE].decode("utf-8", errors="replace")
    if to_eof:
        raw = reader.read_all()
        return raw, raw[:_MAX_BODY_SAMPLE].decode("utf-8", errors="replace")
    return reader.drain(), ""


def _rebuild_head(
    start_line: str,
    headers: list[tuple[str, str]],
    drop: set[str],
    force_close: bool,
    add: list[tuple[str, str]] | None = None,
) -> bytes:
    out = [start_line]
    for k, v in headers:
        if k.lower() in drop or k.lower() in _HOP_BY_HOP:
            continue
        out.append(f"{k}: {v}")
    for k, v in add or []:
        out.append(f"{k}: {v}")
    if force_close:
        out.append("Connection: close")
    return ("\r\n".join(out) + "\r\n\r\n").encode("latin-1")


class HttpProxyListener:
    transport = "http_proxy"
    version = 1

    def __init__(self):
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._stats = {"frames": 0, "exchanges": 0, "refused": 0, "errors": []}

    def start(self, store, capture_id: str, host: str = "127.0.0.1", port: int = 8123, **_) -> dict:
        if self._sock:
            raise TransportError("proxy already running")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
            sock.listen(16)
        except OSError as exc:
            raise TransportError(f"cannot bind {host}:{port}: {exc}") from exc
        sock.settimeout(0.5)
        self._sock = sock
        self._stop.clear()

        def accept_loop():
            while not self._stop.is_set():
                try:
                    client, addr = sock.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                try:
                    self._handle(store, capture_id, client)
                except Exception as exc:  # one bad exchange must not kill the proxy
                    if len(self._stats["errors"]) < 20:
                        self._stats["errors"].append(f"{type(exc).__name__}: {exc}")
                finally:
                    try:
                        client.close()
                    except OSError:
                        pass

        self._thread = threading.Thread(target=accept_loop, daemon=True, name=f"http_proxy:{port}")
        self._thread.start()
        bound = self._sock.getsockname()
        return {
            "bound": f"{bound[0]}:{bound[1]}",
            "status": "proxying",
            "connect_policy": "upstream from the absolute-form request target; CONNECT refused",
        }

    def _handle(self, store, capture_id: str, client: socket.socket) -> None:
        client.settimeout(_READ_TIMEOUT)
        reader = _Reader(client)
        head, found = reader.read_until(b"\r\n\r\n")
        if not found:
            return
        request_line, headers = _split_head(head)
        parts = request_line.split(" ")
        if len(parts) < 3:
            self._respond(client, 400, "malformed request line")
            return
        method, target, version = parts[0], parts[1], parts[2]

        if method.upper() == "CONNECT":
            self._stats["refused"] += 1
            store.append_frame(
                capture_id,
                {
                    "kind_hint": "http_request",
                    "transport": "http_proxy",
                    "direction": "client_to_server",
                    "payload": {
                        "method": "CONNECT",
                        "url": target,
                        "refused": True,
                        "reason": "TLS tunneling is opaque to passive observation; apire refuses rather than pretending",
                    },
                },
            )
            self._stats["frames"] += 1
            self._respond(client, 501, "CONNECT refused: an opaque tunnel is unobservable")
            return

        split = urlsplit(target if "://" in target else f"http://{_header(headers, 'Host')}{target}")
        if not split.hostname:
            self._respond(client, 400, "no upstream host in request target or Host header")
            return
        port = split.port or 80
        path = split.path or "/"
        if split.query:
            path += "?" + split.query
        url = f"http://{split.netloc}{path}"

        request_body_raw, request_sample = _read_body(reader, headers, to_eof=False)

        store.append_frame(
            capture_id,
            {
                "kind_hint": "http_request",
                "transport": "http_proxy",
                "direction": "client_to_server",
                "channel": f"tcp:{split.hostname}:{port}",
                "payload": {
                    "method": method,
                    "url": url,
                    "httpVersion": version,
                    "headers": {k: v for k, v in headers},
                    "postData": request_sample,
                },
            },
        )
        self._stats["frames"] += 1

        try:
            upstream = socket.create_connection((split.hostname, port), timeout=_READ_TIMEOUT)
        except OSError as exc:
            store.append_frame(
                capture_id,
                {
                    "kind_hint": "http_response",
                    "transport": "http_proxy",
                    "direction": "server_to_client",
                    "payload": {"path": split.path or "/", "url": url, "status": 502, "error": str(exc)},
                },
            )
            self._stats["frames"] += 1
            self._respond(client, 502, f"upstream unreachable: {exc}")
            return

        try:
            upstream.settimeout(_READ_TIMEOUT)
            ureader = _Reader(upstream)
            # Host is hop-by-hop-rebuilt, not dropped: Go's http server (and
            # any strict HTTP/1.1 origin) rejects a request without it — a
            # 400-everything bug the ecological tier (Gitea) caught.
            upstream.sendall(
                _rebuild_head(
                    f"{method} {path} {version}",
                    headers,
                    drop={"host"},
                    force_close=True,
                    add=[("Host", split.netloc)],
                )
                + request_body_raw
            )
            resp_head, found = ureader.read_until(b"\r\n\r\n")
            if not found:
                self._respond(client, 502, "upstream closed before responding")
                return
            status_line, resp_headers = _split_head(resp_head)
            tokens = status_line.split(" ")
            status = int(tokens[1]) if len(tokens) > 1 and tokens[1].isdigit() else 0

            if "text/event-stream" in _header(resp_headers, "Content-Type").lower():
                # Streaming responses never complete: relay incrementally and
                # extract events as they arrive. (Without this branch the proxy
                # would block until timeout and break the observed app.)
                self._relay_sse(store, capture_id, client, ureader, status_line, resp_headers, url, split.path or "/")
                return

            resp_body_raw, body_sample = _read_body(ureader, resp_headers, to_eof=True)

            client.sendall(_rebuild_head(status_line, resp_headers, drop=set(), force_close=True) + resp_body_raw)

            store.append_frame(
                capture_id,
                {
                    "kind_hint": "http_response",
                    "transport": "http_proxy",
                    "direction": "server_to_client",
                    "channel": f"tcp:{split.hostname}:{port}",
                    "payload": {
                        "path": split.path or "/",
                        "url": url,
                        "status": status,
                        "mimeType": _header(resp_headers, "Content-Type"),
                        "headers": {k: v for k, v in resp_headers},
                        "body_sample": body_sample,
                    },
                },
            )
            self._stats["frames"] += 1
            self._stats["exchanges"] += 1
        finally:
            try:
                upstream.close()
            except OSError:
                pass

    def _relay_sse(self, store, capture_id: str, client: socket.socket, reader: _Reader, status_line: str, resp_headers, url: str, path: str) -> None:
        """Relay an event-stream incrementally, extracting complete SSE events
        on the way. Runs until the stream ends, the client goes away, or the
        capture stops. Reads go through the reader, never the raw socket: the
        head read may already have buffered early events (a defect this test
        caught the first time)."""
        client.sendall(_rebuild_head(status_line, resp_headers, drop=set(), force_close=True))
        reader.conn.settimeout(_SSE_READ_TIMEOUT)
        buffer = ""
        events: list[dict] = []
        emitted = 0
        while not self._stop.is_set():
            try:
                block = reader.read_some()
            except socket.timeout:
                continue
            except OSError:
                break
            if not block:
                break
            try:
                client.sendall(block)
            except OSError:
                break  # client closed the stream; the relay ends with it
            buffer += block.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
            while "\n\n" in buffer:
                raw_event, _, buffer = buffer.partition("\n\n")
                event = _parse_sse_event(raw_event)
                if event is not None:
                    events.append(
                        {
                            "kind_hint": "sse_event",
                            "transport": "http_proxy",
                            "direction": "server_to_client",
                            "channel": f"tcp:{url.split('//', 1)[-1].split('/', 1)[0]}",
                            "payload": {"path": path, "url": url, **event},
                        }
                    )
                    emitted += 1
                    if len(events) >= 25:
                        store.append_frames(capture_id, events)
                        self._stats["frames"] += len(events)
                        events = []
            if emitted >= _MAX_SSE_EVENTS:
                self._stats["errors"].append(f"sse event cap reached for {path}; further events relayed but not recorded")
                break
        if buffer.strip():
            event = _parse_sse_event(buffer)
            if event is not None:
                events.append(
                    {
                        "kind_hint": "sse_event",
                        "transport": "http_proxy",
                        "direction": "server_to_client",
                        "channel": f"tcp:{url.split('//', 1)[-1].split('/', 1)[0]}",
                        "payload": {"path": path, "url": url, "incomplete": True, **event},
                    }
                )
        if events:
            store.append_frames(capture_id, events)
            self._stats["frames"] += len(events)
        self._stats["sse_events"] = self._stats.get("sse_events", 0) + emitted
        self._stats["exchanges"] += 1

    @staticmethod
    def _respond(client: socket.socket, status: int, message: str) -> None:
        reason = {400: "Bad Request", 501: "Not Implemented", 502: "Bad Gateway"}.get(status, "Error")
        body = message.encode("utf-8")
        client.sendall(
            f"HTTP/1.1 {status} {reason}\r\nContent-Type: text/plain\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
            + body
        )

    def stop(self) -> dict:
        self._stop.set()
        if self._sock:
            self._sock.close()
            self._sock = None
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
        return dict(self._stats)

    def status(self) -> dict:
        return {**self._stats, "listening": self._sock is not None}
