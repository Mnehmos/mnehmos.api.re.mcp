"""UDP observation listener.

Binds a loopback UDP port and decodes what arrives (OSC first — that is the
FL Studio hypothesis). It listens; it never transmits. Frames go through the
store's redaction gate like everything else.
"""

from __future__ import annotations

import socket
import threading

from .. import osc
from ..errors import TransportError


class UdpObserveListener:
    transport = "udp_observe"
    version = 1

    def __init__(self):
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._stats = {"frames": 0, "datagrams": 0, "undecoded": 0, "errors": []}

    def start(self, store, capture_id: str, host: str = "127.0.0.1", port: int = 9000, **_) -> dict:
        if self._sock:
            raise TransportError("listener already running")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind((host, port))
        except OSError as exc:
            raise TransportError(
                f"cannot bind udp {host}:{port}: {exc}",
                hint="the port may be held by the application's own OSC server; pick a free port for it to send TO",
            ) from exc
        sock.settimeout(0.5)
        self._sock = sock
        self._stop.clear()

        def loop():
            while not self._stop.is_set():
                try:
                    data, addr = sock.recvfrom(65536)
                except socket.timeout:
                    continue
                except OSError:
                    break
                self._stats["datagrams"] += 1
                try:
                    msg = osc.decode(data)
                    if msg is None:
                        self._stats["undecoded"] += 1
                        frame = {
                            "kind_hint": "raw",
                            "transport": "udp_observe",
                            "direction": "server_to_client",
                            "channel": f"udp:{addr[0]}:{addr[1]}",
                            "payload": {"raw_hex": data[:256].hex(), "length": len(data)},
                        }
                    else:
                        frame = osc.frame_from_message(msg, channel=f"udp:{addr[0]}:{addr[1]}")
                    store.append_frame(capture_id, frame)
                    self._stats["frames"] += 1
                except Exception as exc:  # a bad datagram must not kill the listener
                    if len(self._stats["errors"]) < 20:
                        self._stats["errors"].append(f"{type(exc).__name__}: {exc}")

        self._thread = threading.Thread(target=loop, daemon=True, name=f"udp_observe:{port}")
        self._thread.start()
        return {"bound": f"{host}:{port}", "status": "listening"}

    def stop(self) -> dict:
        self._stop.set()
        if self._sock:
            self._sock.close()
            self._sock = None
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        return dict(self._stats)

    def status(self) -> dict:
        out = dict(self._stats)
        out["listening"] = self._sock is not None
        return out
