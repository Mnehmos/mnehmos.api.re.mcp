"""Normalization: frames -> the Observation IR.

First principle: the canonical key is the unit the correlator diffs. Two
frames share a canonical key exactly when they are the same observable
behavior (same kind, transport, method, endpoint shape); variable payload
values are facts about a sighting, not about the key.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

_KINDS = {
    "http_request",
    "http_response",
    "ws_frame",
    "sse_event",
    "pipe_message",
    "log_line",
    "osc_message",
    "process_meta",
    "bundle_symbol",
    "raw",
}

# Segments that look like identifiers become template variables.
_ID_SEGMENT_RE = re.compile(r"^[0-9]+$|^[0-9a-fA-F]{8,}$|^[0-9a-f]{8}-[0-9a-f]{4}.*")
# Opaque blobs (base64/encoded URLs/build hashes) also become variables:
# per-sound /waveform/<encoded-cdn-url> and /_next/data/<buildId>/ are one
# observable behavior each, not hundreds.
_OPAQUE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_\-%=]+$")
_WORDLIKE_RE = re.compile(r"^[a-z0-9\-]+$")


def _is_opaque(segment: str) -> bool:
    if "%2f" in segment.lower():
        return True
    if len(segment) < 20 or not _OPAQUE_SEGMENT_RE.match(segment):
        return False
    # all-lowercase-hyphen segments are resource names ("all-trending-packs"),
    # not identifiers
    return not _WORDLIKE_RE.match(segment)


def path_template(path: str) -> str:
    """Collapse identifier-looking path segments into {var}."""
    if not path:
        return path
    parts = path.split("/")
    out = []
    for seg in parts:
        if seg and (_ID_SEGMENT_RE.match(seg) or _is_opaque(seg)):
            out.append("{var}")
        else:
            out.append(seg)
    return "/".join(out)


def shape_signature(value: Any) -> str:
    """A stable type signature over a payload. Values become their type;
    dict keys and list lengths (<=4 sampled) are structure."""
    if isinstance(value, dict):
        inner = ",".join(f"{k}:{shape_signature(v)}" for k, v in sorted(value.items()))
        return "{" + inner + "}"
    if isinstance(value, list):
        seen = []
        for item in value[:4]:
            sig = shape_signature(item)
            if sig not in seen:
                seen.append(sig)
        return "[" + "|".join(seen) + "]"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "str"
    if value is None:
        return "null"
    return "other"


def canonical_key(kind: str, transport: str, method: str, endpoint_template: str, payload_shape: str) -> str:
    basis = json.dumps([kind, transport, method, endpoint_template, payload_shape], separators=(",", ":"))
    return "ck:" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def observation_key_for_frame(frame: dict) -> str:
    """Derive the canonical key from a redacted frame. Kind-specific rules:

    http_request: (method, path template) with query param *names* in the
      shape (values vary); response status folded in for http_response.
    osc_message: the address pattern is the identity.
    process_meta: the event name is the identity.
    """
    kind = frame.get("kind_hint", "raw")
    transport = frame.get("transport", "unknown")
    payload = frame.get("payload", {})
    if kind == "http_request":
        url = str(payload.get("url", ""))
        path = url.split("?", 1)[0].split("//", 1)[-1].split("/", 1)[-1]
        path = "/" + path if not path.startswith("/") else path
        method = str(payload.get("method", "GET")).upper()
        query_names = sorted(_parse_query_names(url))
        shape = "query(" + ",".join(query_names) + ")"
        return canonical_key(kind, transport, method, path_template(path), shape)
    if kind == "http_response":
        path = str(payload.get("path", "/"))
        status_class = str(payload.get("status", 0))[:1] + "xx"
        return canonical_key(kind, transport, "", path_template(path), status_class)
    if kind == "osc_message":
        return canonical_key(kind, transport, "", str(payload.get("address", "/unknown")), str(payload.get("types", "")))
    if kind == "ws_frame" and payload.get("ws_url"):
        # DevTools-attached WS frames are stamped with their connection URL;
        # each connection is its own observable behavior.
        return canonical_key(kind, transport, "", str(payload["ws_url"]), str(payload.get("opcode", "")))
    if kind == "process_meta":
        event = str(payload.get("event", "unknown"))
        # Per-entity events key on the entity's stable identity, not the pid
        # (pids vary run to run; names/paths/module basenames do not).
        if event == "process_present":
            return canonical_key(kind, transport, "", "process:" + str(payload.get("name", "")).lower(), "")
        if event == "module_loaded":
            module = str(payload.get("module", "")).lower()
            return canonical_key(kind, transport, "", "module:" + module, "")
        if event == "socket_listening":
            return canonical_key(
                kind, transport, "", f"socket:{payload.get('proto','')}:{payload.get('local','')}:{payload.get('process','')}", ""
            )
        if event == "connection":
            return canonical_key(
                kind, transport, "",
                f"connection:{payload.get('proto','')}:{payload.get('remote_port',0)}:{payload.get('process','')}", "",
            )
        if event == "pipe_present":
            return canonical_key(kind, transport, "", "pipe:" + str(payload.get("pipe", "")).lower(), "")
        return canonical_key(kind, transport, "", event, "")
    # generic fallback: shape of the whole payload
    return canonical_key(kind, transport, "", "", shape_signature(payload))


def _parse_query_names(url: str) -> list[str]:
    if "?" not in url:
        return []
    query = url.split("?", 1)[1].split("#", 1)[0]
    return [seg.split("=", 1)[0] for seg in query.split("&") if seg]


def _parse_json_sample(sample) -> Any:
    if isinstance(sample, str) and sample.strip()[:1] in ("{", "["):
        try:
            return json.loads(sample)
        except json.JSONDecodeError:
            return None
    return None


def observation_from_group(key: str, frames: list[dict]) -> dict:
    """Build the Observation for one canonical key from its sightings."""
    frames = sorted(frames, key=lambda f: (f.get("ts_utc", ""), f.get("capture_seq", 0)))
    kind = frames[0].get("kind_hint", "raw")
    payload0 = frames[0].get("payload", {})
    payloads = [f.get("payload", {}) for f in frames]
    endpoint = ""
    shape = _induce_shape(payloads)
    if kind == "http_response":
        # Prefer the *decoded body* for schema induction: the payload shell
        # (path/status/headers) is transport plumbing, the body is the API.
        parsed = [p for p in (_parse_json_sample(pl.get("body_sample")) for pl in payloads) if p is not None]
        if parsed:
            shape = _induce_shape(parsed)
        statuses = {str(pl.get("status")) for pl in payloads if pl.get("status") not in (None, 0)}
        if len(statuses) == 1:
            shape = {"status": {"type": "number", "constant": int(next(iter(statuses)))}} | shape
        endpoint = f"HTTP {payload0.get('status', '')} {path_template(str(payload0.get('path', '/')))}".strip()
    elif kind == "http_request":
        parsed = [p for p in (_parse_json_sample(pl.get("postData")) for pl in payloads) if p is not None]
        if parsed:
            shape = {**shape, "request_body": {"type": shape_signature(parsed[0])[:120], "variable": True}}
        url = str(payload0.get("url", "")).split("?", 1)[0].split("//", 1)[-1]
        endpoint = path_template("/" + url.split("/", 1)[-1] if "/" in url else url)
        endpoint = frames[0].get("payload", {}).get("method", "GET").upper() + " " + endpoint
    elif kind == "osc_message":
        endpoint = str(payload0.get("address", ""))
    elif kind == "process_meta":
        event = str(payload0.get("event", ""))
        if event == "process_present":
            endpoint = f"process {payload0.get('name', '')}"
        elif event == "module_loaded":
            endpoint = f"module {payload0.get('module', '')}"
        elif event == "socket_listening":
            endpoint = f"socket {payload0.get('proto', '')} {payload0.get('local', '')} {payload0.get('process', '')}"
        elif event == "connection":
            endpoint = f"connection {payload0.get('proto', '')} :{payload0.get('remote_port', '')} {payload0.get('process', '')}"
        elif event == "pipe_present":
            endpoint = f"pipe {payload0.get('pipe', '')}"
        else:
            endpoint = event
        endpoint = endpoint.strip()
    return {
        "observation_id": "obs_" + hashlib.sha256(key.encode()).hexdigest()[:16],
        "kind": kind,
        "transport": frames[0].get("transport", "unknown"),
        "endpoint_template": endpoint,
        "canonical_key": key,
        "shape": shape,
        "first_seen_utc": frames[0].get("ts_utc"),
        "last_seen_utc": frames[-1].get("ts_utc"),
        "observation_count": len(frames),
        "capture_refs": sorted({f["capture_id"] for f in frames}),
        "sightings": [
            {"capture_id": f["capture_id"], "frame_id": f["frame_id"], "capture_seq": f.get("capture_seq", 0)}
            for f in frames[:200]
        ],
    }


def _induce_shape(payloads: list[dict]) -> dict:
    """Constant fields (same value everywhere) vs variable fields."""
    if not payloads:
        return {}
    shape: dict[str, Any] = {}
    keys = set().union(*(p.keys() for p in payloads if isinstance(p, dict)))
    for k in sorted(keys):
        values = [p.get(k) for p in payloads if isinstance(p, dict) and k in p]
        sigs = {shape_signature(v) for v in values}
        entry: dict[str, Any] = {"type": "/".join(sorted(sigs))[:120]}
        if all(isinstance(v, (str, int, float, bool)) for v in values):
            distinct = {json.dumps(v, default=str) for v in values}
            if len(distinct) == 1:
                entry["constant"] = json.loads(next(iter(distinct)))
            elif len(distinct) <= 8:
                entry["enum_sample"] = sorted(json.loads(d) for d in distinct)
                entry["variable"] = True
            else:
                entry["variable"] = True
        else:
            entry["variable"] = True
        shape[k] = entry
    return shape
