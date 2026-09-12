"""File ingest transport: .har archives and plain-text logs.

Zero sockets. This transport exists so the full ingest->redact->store->
normalize path is exercised before any network listener lands (roadmap M1).
"""

from __future__ import annotations

import json
from pathlib import Path

from ..errors import TransportError

_MAX_BODY_CHARS = 4000


def _headers_dict(header_list) -> dict:
    out = {}
    for h in header_list or []:
        name = h.get("name", "")
        if name:
            out[name] = h.get("value", "")
    return out


class FileIngestListener:
    transport = "file_ingest"
    version = 1

    def __init__(self):
        self._stats = {"frames": 0, "entries": 0, "skipped": 0}

    def start(self, store, capture_id: str, path: str = "", **_) -> dict:
        src = Path(path)
        if not path or not src.is_file():
            raise TransportError(f"file_ingest needs an existing file, got '{path}'")
        suffix = src.suffix.lower()
        if suffix == ".har":
            self._ingest_har(store, capture_id, src)
        elif suffix in (".log", ".txt", ".jsonl"):
            self._ingest_log(store, capture_id, src)
        else:
            raise TransportError(
                f"unsupported ingest file type '{suffix}'",
                supported=[".har", ".log", ".txt", ".jsonl"],
            )
        return {**self._stats, "one_shot": True}

    def _ingest_har(self, store, capture_id: str, src: Path) -> None:
        try:
            har = json.loads(src.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise TransportError(f"unreadable HAR: {exc}") from exc
        entries = har.get("log", {}).get("entries", [])
        for entry in entries:
            req = entry.get("request", {})
            resp = entry.get("response", {})
            url = req.get("url", "")
            path_only = url.split("?", 1)[0].split("//", 1)[-1].split("/", 1)[-1]
            self._frame(
                store,
                capture_id,
                {
                    "kind_hint": "http_request",
                    "payload": {
                        "method": req.get("method", "GET"),
                        "url": url,
                        "httpVersion": req.get("httpVersion", ""),
                        "headers": _headers_dict(req.get("headers")),
                    },
                },
            )
            body = resp.get("content", {}) or {}
            self._frame(
                store,
                capture_id,
                {
                    "kind_hint": "http_response",
                    "payload": {
                        "path": "/" + path_only,
                        "status": resp.get("status", 0),
                        "httpVersion": resp.get("httpVersion", ""),
                        "headers": _headers_dict(resp.get("headers")),
                        "body_chars": len(body.get("text") or ""),
                        "body_sample": (body.get("text") or "")[:_MAX_BODY_CHARS],
                    },
                },
            )
            self._stats["entries"] += 1
        self._stats["skipped"] = len(entries) - self._stats["entries"]

    def _ingest_log(self, store, capture_id: str, src: Path) -> None:
        for i, line in enumerate(src.read_text(encoding="utf-8", errors="replace").splitlines()):
            if not line.strip():
                continue
            self._frame(
                store,
                capture_id,
                {
                    "kind_hint": "log_line",
                    "payload": {"line_no": i, "line": line[:_MAX_BODY_CHARS]},
                },
            )

    def _frame(self, store, capture_id: str, frame: dict) -> None:
        frame.setdefault("transport", "file_ingest")
        frame.setdefault("direction", "unspecified")
        store.append_frame(capture_id, frame)
        self._stats["frames"] += 1

    def stop(self) -> dict:
        return dict(self._stats)

    def status(self) -> dict:
        return {**self._stats, "listening": False, "one_shot": True}
