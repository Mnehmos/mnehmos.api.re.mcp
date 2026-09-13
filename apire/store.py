"""The capture store and evidence KB root (ADR-007).

Two kinds of state with opposite requirements:

- Raw frames: immutable, append-only JSONL manifests per capture. Frames pass
  the redaction gate *here*, inside append_frame, because the store is the
  thing that must be clean — a transport that forgets to redact cannot bypass
  this.
- The KB (kb.json): capture records + evidence claims, revised over time,
  atomic writes with one-generation .bak, StoreError on corruption.

Capture start without an authorization statement raises PolicyError: that is
a schema-required parameter, not prompt theater.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .errors import PolicyError, StoreError
from .normalize import observation_from_group, observation_key_for_frame
from .redaction import redact_frame

SCHEMA = 1
_KNOWN_TRANSPORTS = {
    "http_proxy",
    "log_tail",
    "file_ingest",
    "devtools_attach",
    "udp_observe",
    "process_meta",
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _uid(prefix: str, n: int = 12) -> str:
    return prefix + secrets.token_hex(n // 2)


class Store:
    """Root of apire_kb/: capture manifests + kb.json. Thread-safe frame
    appends (listeners own threads); atomic KB writes."""

    def __init__(self, root: str | Path | None = None, salt: bytes | None = None):
        import os as _os

        base = Path(root) if root else Path(_os.environ.get("APIRE_KB") or (Path.cwd() / "apire_kb"))
        self.root = base
        self.captures_dir = base / "captures"
        self.kb_path = base / "kb.json"
        self.captures_dir.mkdir(parents=True, exist_ok=True)
        self.salt = salt if salt is not None else self._env_salt()
        self._lock = threading.Lock()
        self._kb = self._load_kb()

    # ------------------------------------------------------------ salt

    @staticmethod
    def _env_salt() -> bytes | None:
        raw = os.environ.get("APIRE_REDACTION_SALT", "")
        return bytes.fromhex(raw) if raw else None

    def salt_fingerprint(self) -> str:
        if not self.salt:
            return "none"
        return hashlib.sha256(self.salt).hexdigest()[:16]

    # ------------------------------------------------------------ kb io

    def _load_kb(self) -> dict:
        if not self.kb_path.exists():
            return {"schema": SCHEMA, "salt_fingerprint": self.salt_fingerprint(), "captures": {}, "claims": []}
        try:
            kb = json.loads(self.kb_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise StoreError(f"evidence KB at {self.kb_path} is unreadable: {exc}") from exc
        fp = self.salt_fingerprint()
        if kb.get("salt_fingerprint") not in (fp, "none"):
            raise StoreError(
                f"redaction salt changed: KB was written under fingerprint "
                f"{kb.get('salt_fingerprint')}, current salt is {fp}. Pseudonyms from older "
                "captures cannot be correlated; restore the original APIRE_REDACTION_SALT "
                "or start a fresh KB."
            )
        kb.setdefault("captures", {})
        kb.setdefault("claims", [])
        if not kb.get("salt_fingerprint") or kb.get("salt_fingerprint") == "none":
            kb["salt_fingerprint"] = fp
        return kb

    def _save_kb(self) -> None:
        self._kb["salt_fingerprint"] = self.salt_fingerprint() or "none"
        self.kb_path.parent.mkdir(parents=True, exist_ok=True)
        if self.kb_path.exists():
            bak = self.kb_path.with_suffix(self.kb_path.suffix + ".bak")
            bak.write_text(self.kb_path.read_text(encoding="utf-8"), encoding="utf-8")
        fd, tmp = tempfile.mkstemp(dir=str(self.kb_path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._kb, fh, indent=1)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.kb_path)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # ------------------------------------------------------------ captures

    def start_capture(
        self,
        transport: str,
        name: str = "",
        authorization_statement: str = "",
        hypothesis: str = "",
        instrument: str = "",
    ) -> dict:
        if not (authorization_statement or "").strip():
            raise PolicyError(
                "capture refused: authorization_statement is required and must be non-empty",
                hint="state what you are authorized to inspect; it is stored with the session",
            )
        if transport not in _KNOWN_TRANSPORTS:
            raise PolicyError(f"unknown transport '{transport}'", vocabulary=sorted(_KNOWN_TRANSPORTS))
        with self._lock:
            session_id = self._kb.get("session_id") or _uid("sess_")
            self._kb["session_id"] = session_id
            self._kb.setdefault("authorization_statement_fingerprint", hashlib.sha256(authorization_statement.encode()).hexdigest()[:16])
            cap = {
                "capture_id": _uid("cap_"),
                "session_id": session_id,
                "name": name or transport,
                "label": "",
                "hypothesis": hypothesis,
                "transport": transport,
                "instrument": instrument or f"{transport}/v1",
                "authorization_statement_fingerprint": hashlib.sha256(authorization_statement.encode()).hexdigest()[:16],
                "started_utc": _now(),
                "ended_utc": None,
                "frame_count": 0,
                "bytes_total": 0,
                "notes": [],
            }
            self._kb["captures"][cap["capture_id"]] = cap
            self._save_kb()
        (self.captures_dir / cap["capture_id"]).mkdir(parents=True, exist_ok=True)
        return dict(cap)

    def append_frame(self, capture_id: str, frame: dict) -> str:
        return self.append_frames(capture_id, [frame])[0]

    def append_frames(self, capture_id: str, frames: list[dict]) -> list[str]:
        """Batch append: one fsync and one KB save per batch. Per-frame
        fsync does not scale to snapshot transports that emit one frame per
        process/socket/module."""
        if not frames:
            return []
        with self._lock:
            cap = self._kb["captures"].get(capture_id)
            if cap is None:
                raise StoreError(f"unknown capture '{capture_id}'")
            if cap["ended_utc"]:
                raise StoreError(
                    f"capture '{capture_id}' ended at {cap['ended_utc']}; evidence is append-only within a capture"
                )
            mode = "pseudonymize" if self.salt else "redact"
            manifest = self.captures_dir / capture_id / "manifest.jsonl"
            ids: list[str] = []
            total = 0
            with open(manifest, "a", encoding="utf-8") as fh:
                for frame in frames:
                    red, report = redact_frame(frame, mode=mode, salt=self.salt)
                    red["capture_id"] = capture_id
                    red["capture_seq"] = cap["frame_count"]
                    red["frame_id"] = _uid("frm_", 16)
                    red["ts_utc"] = red.get("ts_utc") or _now()
                    red["payload_sha256"] = hashlib.sha256(
                        json.dumps(red.get("payload", {}), sort_keys=True, default=str).encode()
                    ).hexdigest()
                    if report["classes_fired"]:
                        red["redaction_report"] = report
                    line = json.dumps(red, separators=(",", ":"), default=str)
                    fh.write(line + "\n")
                    cap["frame_count"] += 1
                    total += len(line)
                    ids.append(red["frame_id"])
                fh.flush()
                os.fsync(fh.fileno())
            cap["bytes_total"] += total
            self._save_kb()
            return ids

    def stop_capture(self, capture_id: str) -> dict:
        with self._lock:
            cap = self._kb["captures"].get(capture_id)
            if cap is None:
                raise StoreError(f"unknown capture '{capture_id}'")
            if not cap["ended_utc"]:
                cap["ended_utc"] = _now()
                self._save_kb()
            return dict(cap)

    def list_captures(self) -> list[dict]:
        return sorted(self._kb["captures"].values(), key=lambda c: c["started_utc"])

    def get_capture(self, capture_id: str) -> dict:
        cap = self._kb["captures"].get(capture_id)
        if cap is None:
            raise StoreError(f"unknown capture '{capture_id}'")
        return dict(cap)

    def label(self, capture_id: str, label: str, hypothesis: str | None = None) -> dict:
        cap = self.get_capture(capture_id)
        cap["label"] = label
        if hypothesis is not None:
            cap["hypothesis"] = hypothesis
        with self._lock:
            self._kb["captures"][capture_id] = cap
            self._save_kb()
        return cap

    def note(self, capture_id: str, seq: int, text: str) -> dict:
        cap = self.get_capture(capture_id)
        cap["notes"].append({"seq": seq, "note_utc": _now(), "text": text})
        with self._lock:
            self._kb["captures"][capture_id] = cap
            self._save_kb()
        return cap

    def frames(self, capture_id: str) -> list[dict]:
        self.get_capture(capture_id)
        manifest = self.captures_dir / capture_id / "manifest.jsonl"
        if not manifest.exists():
            return []
        out = []
        for line in manifest.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def iter_frames(self, capture_ids: list[str] | None = None) -> Iterator[dict]:
        for cap in self.list_captures():
            if capture_ids and cap["capture_id"] not in capture_ids:
                continue
            yield from self.frames(cap["capture_id"])

    # ------------------------------------------------------------ observations

    def build_observations(self, capture_ids: list[str]) -> dict[str, dict]:
        """Group frames by canonical key into Observations."""
        groups: dict[str, list[dict]] = {}
        for cap_id in capture_ids:
            for frame in self.frames(cap_id):
                key = observation_key_for_frame(frame)
                groups.setdefault(key, []).append(frame)
        return {key: observation_from_group(key, fs) for key, fs in groups.items()}

    def find_observation(self, observation_id: str) -> dict | None:
        for obs in self.build_observations(list(self._kb["captures"])).values():
            if obs["observation_id"] == observation_id:
                return obs
        return None

    # ------------------------------------------------------------ claims

    def all_claims(self) -> list[dict]:
        return list(self._kb.get("claims", []))

    def upsert_claim(self, claim: dict) -> None:
        """Replace by claim_id (history handled by caller), atomically."""
        with self._lock:
            claims = self._kb.setdefault("claims", [])
            for i, existing in enumerate(claims):
                if existing["claim_id"] == claim["claim_id"]:
                    claims[i] = claim
                    break
            else:
                claims.append(claim)
            self._save_kb()
