"""Shared export machinery.

Every exported element carries its evidence: a semantic claim's level and
confidence where one exists, or an explicit "presence in captured traffic"
(OBSERVED, 0.80) where none does. Elements whose evidence sits below the
caller's floor are moved to a speculative section — never silently mixed in
with observed fact.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from .. import kb

LEVEL_ORDER = {level: i for i, (level, _, _) in enumerate(kb.LEVELS)}
DEFAULT_FLOOR = "INFERRED"


def admits(level: str, min_level: str) -> bool:
    return LEVEL_ORDER.get(level, 99) <= LEVEL_ORDER.get(min_level, LEVEL_ORDER[DEFAULT_FLOOR])


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_") or "unnamed"


def claims_by_subject(store) -> dict[str, dict]:
    """Best semantic_name claim per subject (highest confidence)."""
    out: dict[str, dict] = {}
    for claim in store.all_claims():
        if claim["kind"] != "semantic_name":
            continue
        current = out.get(claim["subject"])
        if current is None or claim["confidence"] > current["confidence"]:
            out[claim["subject"]] = claim
    return out


def evidence_block(obs: dict, claim: dict | None) -> dict:
    if claim:
        return {
            "level": claim["level"],
            "confidence": claim["confidence"],
            "claim_id": claim["claim_id"],
            "semantic": claim["value"],
            "captures": obs["capture_refs"],
            "basis": "semantic claim backed by verified provenance (see api_re_evidence explain)",
        }
    return {
        "level": "OBSERVED",
        "confidence": 0.80,
        "claim_id": None,
        "semantic": None,
        "captures": obs["capture_refs"],
        "basis": "presence in captured traffic; no semantic claim yet",
    }


# ---------------------------------------------------------------- shape -> schema


def _split_top(text: str, sep: str) -> list[str]:
    parts, depth, current = [], 0, []
    for ch in text:
        if ch in "[{(":
            depth += 1
        elif ch in "]})":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current))
    return parts


_SCALARS = {"str": "string", "number": "number", "bool": "boolean", "null": "null"}


def parse_sig(sig: str) -> dict:
    """Parse a shape signature produced by normalize.shape_signature into a
    JSON Schema fragment. Our own format, so a small recursive parser."""
    sig = (sig or "").strip()
    if sig.startswith("["):
        inner = sig[1:-1].strip()
        if not inner:
            return {"type": "array"}
        variants = [parse_sig(p) for p in _split_top(inner, "|") if p.strip()]
        items: Any = variants[0] if len(variants) == 1 else {"anyOf": variants}
        return {"type": "array", "items": items}
    if sig.startswith("{"):
        props = {}
        for pair in _split_top(sig[1:-1], ","):
            if ":" in pair:
                key, _, value = pair.partition(":")
                props[key.strip()] = parse_sig(value)
        return {"type": "object", "properties": props}
    if sig in _SCALARS:
        return {"type": _SCALARS[sig]}
    return {}


def shape_to_schema(shape: dict) -> dict:
    """Induced observation shape -> JSON Schema object fragment."""
    props: dict[str, dict] = {}
    for key, entry in shape.items():
        if key.startswith("@"):
            continue  # body metadata, not a field
        raw_type = str(entry.get("type", ""))
        variants = [parse_sig(p) for p in _split_top(raw_type, "/") if p.strip()]
        variants = [v for v in variants if v]
        if not variants:
            fragment: dict = {}
        elif len(variants) == 1:
            fragment = variants[0]
        else:
            fragment = {"anyOf": variants}
        if "constant" in entry:
            fragment["const"] = entry["constant"]
        if entry.get("variable"):
            fragment["x-apire-variable"] = True
        if entry.get("enum_sample"):
            fragment["examples"] = entry["enum_sample"][:8]
        props[key] = fragment
    return {"type": "object", "properties": props}


def body_shape_to_schema(shape: dict) -> dict:
    """Body schema for a response observation: handles the "@body" array
    representation (items signature parsed into a real schema) and object
    bodies alike."""
    meta = shape.get("@body")
    if meta and meta.get("type") == "array":
        items_sig = meta.get("items_sig") or "other"
        schema = {"type": "array", "items": parse_sig(items_sig)}
        if meta.get("lengths"):
            schema["x-apire-lengths-observed"] = meta["lengths"]
        return schema
    return shape_to_schema(shape)


# ---------------------------------------------------------------- frame context


def frame_context(store, capture_ids: list[str] | None = None) -> dict:
    """One pass over frames: per-canonical-key host, direction, ws url, URL."""
    from ..normalize import observation_key_for_frame

    caps = capture_ids if capture_ids else [c["capture_id"] for c in store.list_captures()]
    ctx: dict[str, dict] = {}
    for frame in store.iter_frames(caps):
        key = observation_key_for_frame(frame)
        entry = ctx.setdefault(key, {"host": "", "direction": "", "ws_url": "", "url": "", "chars": 0})
        payload = frame.get("payload", {})
        if not entry["direction"]:
            entry["direction"] = frame.get("direction", "")
        if payload.get("url") and not entry["url"]:
            entry["url"] = payload["url"]
            tail = payload["url"].split("//", 1)[-1]
            entry["host"] = tail.split("/", 1)[0]
        if payload.get("ws_url") and not entry["ws_url"]:
            entry["ws_url"] = payload["ws_url"]
        entry["chars"] += len(str(payload.get("payloadData", "")))
    return ctx


# ---------------------------------------------------------------- row collectors


def endpoint_rows(store, capture_ids: list[str] | None, claims: dict[str, dict]) -> list[dict]:
    caps = capture_ids if capture_ids else [c["capture_id"] for c in store.list_captures()]
    obs = store.build_observations(caps)
    ctx = frame_context(store, caps)
    responses: dict[str, list[dict]] = {}
    for o in obs.values():
        if o["kind"] != "http_response":
            continue
        template = o["endpoint_template"]  # "HTTP 200 /path"
        parts = template.split(" ", 2)
        if len(parts) == 3:
            path = parts[2]
            responses.setdefault(path, []).append(
                {"status": parts[1], "observation_id": o["observation_id"], "shape": o["shape"]}
            )
    rows = []
    for key, o in obs.items():
        if o["kind"] != "http_request":
            continue
        template = o["endpoint_template"]
        method, _, path = template.partition(" ")
        ctx_entry = ctx.get(key, {})
        # Claims may sit on the request observation *or* on any of its
        # response observations (bodies often carry the evidence); the best
        # supported reading wins, whichever side it was proposed on.
        response_entries = responses.get(path, [])
        candidates = [claims.get(o["observation_id"])] + [claims.get(r["observation_id"]) for r in response_entries]
        candidates = [c for c in candidates if c]
        claim = max(candidates, key=lambda c: c["confidence"]) if candidates else None
        evidence = evidence_block(o, claim)
        if claim:
            evidence["claim_subject"] = claim["subject"]
        rows.append(
            {
                "observation_id": o["observation_id"],
                "canonical_key": key,
                "transport": o["transport"],
                "method": method or "GET",
                "path": path or "/",
                "host": ctx_entry.get("host", ""),
                "url_example": ctx_entry.get("url", ""),
                "sightings": o["observation_count"],
                "shape": o["shape"],
                "responses": response_entries,
                "evidence": evidence,
            }
        )
    rows.sort(key=lambda r: (-r["sightings"], r["path"]))
    return rows


def message_rows(store, capture_ids: list[str] | None, claims: dict[str, dict]) -> list[dict]:
    caps = capture_ids if capture_ids else [c["capture_id"] for c in store.list_captures()]
    obs = store.build_observations(caps)
    ctx = frame_context(store, caps)
    rows = []
    for key, o in obs.items():
        if o["kind"] not in ("ws_frame", "osc_message", "pipe_message", "sse_event"):
            continue
        ctx_entry = ctx.get(key, {})
        channel = o["endpoint_template"] or ctx_entry.get("ws_url") or key
        claim = claims.get(o["observation_id"])
        rows.append(
            {
                "observation_id": o["observation_id"],
                "canonical_key": key,
                "transport": o["transport"],
                "channel": channel,
                "direction": ctx_entry.get("direction", ""),
                "sightings": o["observation_count"],
                "shape": o["shape"],
                "evidence": evidence_block(o, claim),
            }
        )
    rows.sort(key=lambda r: -r["sightings"])
    return rows


def split_by_floor(rows: list[dict], min_level: str) -> tuple[list[dict], list[dict]]:
    accepted = [r for r in rows if admits(r["evidence"]["level"], min_level)]
    speculative = [r for r in rows if not admits(r["evidence"]["level"], min_level)]
    return accepted, speculative


def hosts(rows: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for row in rows:
        host = row.get("host") or "(unknown)"
        counts[host] = counts.get(host, 0) + row["sightings"]
    return [{"host": h, "sightings": n} for h, n in sorted(counts.items(), key=lambda kv: -kv[1])]
