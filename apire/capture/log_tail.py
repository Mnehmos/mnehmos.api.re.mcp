"""Log tailing transport.

Passive by definition: the application writes its log; we read it. Follows
the file from its current end, emitting one frame per appended line.
Rotation and truncation are handled (size decrease resets to offset 0).
Polling, not change-notification APIs — no dependencies, predictable on
Windows, and a half-second of latency is irrelevant to observation.
"""

from __future__ import annotations

import threading
from pathlib import Path

from ..errors import TransportError


class LogTailListener:
    transport = "log_tail"
    version = 1

    def __init__(self):
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._path: Path | None = None
        self._pos = 0
        self._stats = {"frames": 0, "rotations": 0, "errors": []}

    def start(self, store, capture_id: str, path: str = "", poll_seconds: float = 0.25, **_) -> dict:
        if self._thread:
            raise TransportError("log tail already running")
        src = Path(path)
        if not path or not src.is_file():
            raise TransportError(f"log_tail needs an existing file, got '{path}'")
        self._path = src
        self._pos = src.stat().st_size  # follow from the end; history belongs to file_ingest
        self._stop.clear()

        def loop():
            while not self._stop.is_set():
                try:
                    size = src.stat().st_size
                except FileNotFoundError:
                    # rotation gap: the file may come back
                    self._stop.wait(poll_seconds)
                    continue
                if size < self._pos:
                    self._stats["rotations"] += 1
                    self._pos = 0
                if size > self._pos:
                    try:
                        with open(src, "r", encoding="utf-8", errors="replace") as fh:
                            fh.seek(self._pos)
                            data = fh.read()
                            self._pos = fh.tell()
                    except OSError as exc:
                        if len(self._stats["errors"]) < 10:
                            self._stats["errors"].append(f"{type(exc).__name__}: {exc}")
                        self._stop.wait(poll_seconds)
                        continue
                    lines = [ln for ln in data.splitlines() if ln.strip()]
                    if lines:
                        frames = [
                            {
                                "kind_hint": "log_line",
                                "transport": "log_tail",
                                "direction": "unspecified",
                                "channel": str(src),
                                "payload": {"line": line[:4000]},
                            }
                            for line in lines
                        ]
                        store.append_frames(capture_id, frames)
                        self._stats["frames"] += len(frames)
                self._stop.wait(poll_seconds)

        self._thread = threading.Thread(target=loop, daemon=True, name="log_tail")
        self._thread.start()
        return {"following": str(src), "from_offset": self._pos, "status": "tailing"}

    def stop(self) -> dict:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        return dict(self._stats)

    def status(self) -> dict:
        return {**self._stats, "following": str(self._path) if self._path else "", "position": self._pos, "listening": self._thread is not None}
