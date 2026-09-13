"""Redaction at ingestion (ADR-004).

First principle: the spec table decides, not judgment. Credential material is
removed or pseudonymized here, before the frame's bytes exist anywhere, so
there is no window in which the secret is stored. The store learns
`Authorization: <REDACTED>`, never the credential.

Modes:
  redact      (no salt): credential values -> <REDACTED>, full stop.
  pseudonymize (salt):   pseudonymizable values -> "~:" + HMAC-SHA256(salt, value)[:16].
                       Equality survives (session correlation across captures);
                       the value does not.

The report records classes and counts — never values.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from typing import Any

REDACTED = "<REDACTED>"
PSEUDONYM_PREFIX = "~:"

# Header names whose entire value is credential material.
HEADER_DENYLIST = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "x-csrf-token",
    "x-session-id",
}

# Key-name fragments (case-insensitive, last path segment) whose values are
# sensitive; these are the pseudonymizable class.
SENSITIVE_KEY_FRAGMENTS = (
    "token",
    "key",
    "secret",
    "password",
    "credential",
    "session",
    "sig",
    "nonce",
    "api_key",
)

# Value shapes that are credential material regardless of key name.
_JWT_RE = re.compile(r"^eyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{4,}$")
_BEARER_RE = re.compile(r"^(Bearer|Basic|token)\s+\S{8,}$", re.IGNORECASE)
_LONG_HEX_RE = re.compile(r"^[0-9a-fA-F]{32,}$")
_LONG_B64_RE = re.compile(r"^[A-Za-z0-9+/=]{40,}$")
_AWS_KEY_RE = re.compile(r"^AKIA[0-9A-Z]{16}$")
_TOKEN_PREFIX_RE = re.compile(r"^(sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,})")

# Credential shapes that can appear *embedded* inside log lines and long
# strings. Whole-value patterns (long hex/base64) are deliberately not here:
# scanning every substring for those would redact half of any log file.
_EMBEDDED_RE = re.compile(
    r"(sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}"
    r"|eyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{4,}"
    r"|(?:Bearer|Basic|token)\s+\S{8,})"
)


def _looks_credential(value: str) -> bool:
    v = value.strip()
    return bool(
        _JWT_RE.match(v)
        or _BEARER_RE.match(v)
        or _AWS_KEY_RE.match(v)
        or _TOKEN_PREFIX_RE.match(v)
        or _LONG_HEX_RE.match(v)
        or _LONG_B64_RE.match(v)
    )


def _strip_embedded(value: str) -> str:
    if not _EMBEDDED_RE.search(value):
        return value
    return _EMBEDDED_RE.sub(REDACTED, value)


def _redact_url_query(value: str, mode: str, salt: bytes | None, report: _Report) -> str:
    """URLs carry credentials in query strings (?token=..., ?sig=...)."""
    if "?" not in value or "=" not in value.split("?", 1)[1]:
        return value
    base, _, query = value.partition("?")
    frag = ""
    if "#" in query:
        query, _, frag = query.partition("#")
    parts = []
    for seg in query.split("&"):
        if "=" in seg:
            name, _, val = seg.partition("=")
            if _is_sensitive_key(name) and val:
                parts.append(f"{name}={_redact_value(val, name, mode, salt, report)}")
            else:
                parts.append(seg)
        else:
            parts.append(seg)
    return "?".join([base, "&".join(parts) + ("#" + frag if frag else "")])


def _last_segment(key: str) -> str:
    return re.split(r"[.\[\]\/]", key)[-1].lower()


def _is_sensitive_key(key: str) -> bool:
    seg = _last_segment(key)
    return any(frag in seg for frag in SENSITIVE_KEY_FRAGMENTS)


def _pseudonym(value: str, salt: bytes) -> str:
    digest = hmac.new(salt, value.encode("utf-8"), hashlib.sha256).hexdigest()[:16]
    return PSEUDONYM_PREFIX + digest


class _Report:
    def __init__(self) -> None:
        self.classes: dict[str, int] = {}
        self.redacted = 0
        self.pseudonymized = 0

    def fire(self, cls: str, how: str) -> None:
        self.classes[cls] = self.classes.get(cls, 0) + 1
        if how == "pseudonymize":
            self.pseudonymized += 1
        else:
            self.redacted += 1

    def to_dict(self) -> dict:
        return {
            "classes_fired": dict(self.classes),
            "redacted_values": self.redacted,
            "pseudonymized_values": self.pseudonymized,
        }


def _redact_value(value: str, key: str, mode: str, salt: bytes | None, report: _Report) -> str:
    if _looks_credential(value):
        report.fire("credential_shape", "redact")
        return REDACTED
    if _last_segment(key) in {"authorization", "proxy-authorization", "cookie", "set-cookie"}:
        report.fire("header_denylist", "redact")
        return REDACTED
    if _is_sensitive_key(key) and mode == "pseudonymize" and salt:
        report.fire("sensitive_key", "pseudonymize")
        return _pseudonym(value, salt)
    if _is_sensitive_key(key):
        report.fire("sensitive_key", "redact")
        return REDACTED
    return value


def _walk(obj: Any, key: str, mode: str, salt: bytes | None, report: _Report) -> Any:
    if isinstance(obj, dict):
        return {k: _walk(v, str(k), mode, salt, report) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk(item, key, mode, salt, report) for item in obj]
    if isinstance(obj, str):
        # One path for every string: scrub embedded credentials (log lines),
        # URLs carrying credential-shaped query values, whole-value shapes,
        # then key-name rules.
        scrubbed = _strip_embedded(obj)
        if "://" in scrubbed or scrubbed.startswith("?"):
            scrubbed = _redact_url_query(scrubbed, mode, salt, report)
        # A *string* that is itself JSON (postData, HAR body_sample, log
        # payloads) must be parsed and key-name-redacted recursively — a
        # password inside a JSON body string is still a password (caught by
        # the ecological tier: Gitea's signin POST leaked to the manifest).
        parsed = _try_json(scrubbed)
        if parsed is not None:
            redacted = _walk(parsed, key, mode, salt, report)
            return json.dumps(redacted, separators=(",", ":"), default=str)
        return _redact_value(scrubbed, key, mode, salt, report)
    return obj


def _try_json(text: str) -> Any | None:
    head = text.lstrip()[:1]
    if head not in ("{", "["):
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def redact_frame(frame: dict, mode: str = "redact", salt: bytes | None = None) -> tuple[dict, dict]:
    """Return (redacted_frame_copy, report_dict). The input frame is not mutated;
    the caller persists only the redacted copy."""
    if mode not in ("redact", "pseudonymize"):
        raise ValueError(f"unknown redaction mode: {mode}")
    if mode == "pseudonymize" and not salt:
        raise ValueError("pseudonymize mode requires a salt")
    report = _Report()
    red = _walk(frame, "", mode, salt, report)
    fired = sorted(report.classes)
    red["redacted"] = bool(fired)
    red["redaction_classes_fired"] = fired
    return red, report.to_dict()
