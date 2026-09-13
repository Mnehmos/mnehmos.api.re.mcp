"""Candidate MCP surface export.

Derives proposed semantic capabilities from the evidence graph — the
user-facing point of the whole exercise (``GET /projects/{id}`` +
``WS project.updated`` becoming ``project.get`` / ``project.events``).

This is a specification of a capability surface, never an implementation of
calls. There is no transport in this document and no action that sends
anything; a human consumes this to decide which surfaces to build, and the
normal RE workflow decides which deserve to exist.
"""

from __future__ import annotations

from .common import DEFAULT_FLOOR, claims_by_subject, endpoint_rows, message_rows, slug, split_by_floor, utcnow


def _tool_key(evidence: dict, fallback: str) -> str:
    semantic = evidence.get("semantic")
    if semantic:
        parts = semantic.split(".")
        return slug("_".join(parts[:2])) if len(parts) > 1 else slug(parts[0])
    return slug(fallback)


def _action_name(evidence: dict, method: str, path: str) -> str:
    semantic = evidence.get("semantic")
    if semantic:
        parts = semantic.split(".")
        if len(parts) > 2:
            return slug("_".join(parts[2:]))
        return slug(parts[-1])
    tail = path.strip("/").split("/")[-1] or "root"
    if tail == "{var}" or len(tail) > 40:
        # opaque tail: build the name from the meaningful prefix instead
        segments = [s for s in path.strip("/").split("/") if s and s != "{var}"]
        tail = segments[-1] if segments else "root"
    return slug(f"{method.lower()}_{tail}")


def _add_action(entry: dict, action: dict) -> None:
    """Merge same-purpose actions (one endpoint can appear under several
    canonical keys when payload shapes differ) into a single action that
    keeps every observation id and the best evidence."""
    key = (action["action"], action.get("http") or action.get("channel") or "")
    existing = entry["_actions"].get(key)
    if existing is None:
        action["observation_ids"] = [action.pop("observation_id")]
        entry["_actions"][key] = action
        return
    existing["observation_ids"].append(action.pop("observation_id"))
    existing["sightings"] = existing.get("sightings", 0) + action.get("sightings", 0)
    if action["evidence"]["confidence"] > existing["evidence"]["confidence"]:
        existing["evidence"] = action["evidence"]


def mcp_candidate_document(store, capture_ids: list[str] | None = None, min_level: str = DEFAULT_FLOOR) -> dict:
    claims = claims_by_subject(store)
    endpoints = endpoint_rows(store, capture_ids, claims)
    messages = message_rows(store, capture_ids, claims)
    accepted_ep, spec_ep = split_by_floor(endpoints, min_level)
    accepted_ms, spec_ms = split_by_floor(messages, min_level)

    tools: dict[str, dict] = {}
    for row in accepted_ep:
        tool = _tool_key(row["evidence"], row["host"] or "observed_http")
        entry = tools.setdefault(
            tool,
            {
                "name": tool,
                "kind": "http",
                "description": f"capabilities observed on {row['host'] or 'the target'}",
                "_actions": {},
            },
        )
        _add_action(
            entry,
            {
                "action": _action_name(row["evidence"], row["method"], row["path"]),
                "http": f"{row['method']} {row['path']}",
                "evidence": row["evidence"],
                "observation_id": row["observation_id"],
                "sightings": row["sightings"],
            },
        )
    for row in accepted_ms:
        tool = _tool_key(row["evidence"], row["transport"] or "observed_events")
        entry = tools.setdefault(
            tool,
            {
                "name": tool,
                "kind": "events",
                "description": "observed asynchronous surface",
                "_actions": {},
            },
        )
        _add_action(
            entry,
            {
                "action": _action_name(row["evidence"], "event", row["channel"]),
                "channel": row["channel"],
                "direction_observed": row["direction"],
                "evidence": row["evidence"],
                "observation_id": row["observation_id"],
                "sightings": row["sightings"],
            },
        )

    for entry in tools.values():
        actions = sorted(entry.pop("_actions").values(), key=lambda a: a["action"])
        entry["actions"] = actions
        levels = [a["evidence"]["level"] for a in actions]
        from .common import LEVEL_ORDER

        entry["best_level"] = sorted(levels, key=lambda lvl: LEVEL_ORDER.get(lvl, 99))[0]

    return {
        "apire_mcp_candidate": 1,
        "generated_utc": utcnow(),
        "generator": "apire export mcp_candidate",
        "min_level": min_level,
        "candidate_tools": sorted(tools.values(), key=lambda t: t["name"]),
        "speculative": {
            "http": [{"method": r["method"], "path": r["path"], "evidence": r["evidence"]} for r in spec_ep],
            "events": [{"channel": r["channel"], "evidence": r["evidence"]} for r in spec_ms],
        },
        "guarantee": (
            "This document specifies capabilities; it implements none. apire has no action "
            "that sends anything to the observed application, and this export contains no "
            "transport definition — building from it is a deliberate, separate act."
        ),
    }
