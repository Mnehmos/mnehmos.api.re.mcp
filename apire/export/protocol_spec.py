"""Protocol catalog export: apire's own format.

Not every observed fact fits OpenAPI/AsyncAPI (transport mix, error
semantics, authentication posture, evidence levels). This document is the
honest catalog: transports, endpoints, messages, error responses, and what
is still unknown.
"""

from __future__ import annotations

from .common import DEFAULT_FLOOR, claims_by_subject, endpoint_rows, hosts, message_rows, split_by_floor, utcnow


def protocol_spec_document(store, capture_ids: list[str] | None = None, min_level: str = DEFAULT_FLOOR) -> dict:
    claims = claims_by_subject(store)
    endpoints = endpoint_rows(store, capture_ids, claims)
    messages = message_rows(store, capture_ids, claims)
    accepted_ep, spec_ep = split_by_floor(endpoints, min_level)
    accepted_ms, spec_ms = split_by_floor(messages, min_level)

    transports: dict[str, dict] = {}
    for row in endpoints + messages:
        t = row.get("transport") or "unknown"
        entry = transports.setdefault(t, {"transport": t, "elements": 0, "sightings": 0})
        entry["elements"] += 1
        entry["sightings"] += row["sightings"]

    errors = []
    for row in accepted_ep:
        for resp in row["responses"]:
            if str(resp["status"]).startswith(("4", "5")):
                errors.append(
                    {
                        "method": row["method"],
                        "path": row["path"],
                        "status": resp["status"],
                        "evidence": {**row["evidence"], "observation_id": resp["observation_id"]},
                    }
                )

    # Responses whose request was never captured (window boundary, filtered
    # transport): catalog them instead of dropping them silently.
    caps = capture_ids if capture_ids else [c["capture_id"] for c in store.list_captures()]
    obs = store.build_observations(caps)
    matched_ids = {resp["observation_id"] for row in endpoints for resp in row["responses"]}
    unmatched = []
    for o in obs.values():
        if o["kind"] != "http_response" or o["observation_id"] in matched_ids:
            continue
        parts = o["endpoint_template"].split(" ", 2)
        unmatched.append(
            {
                "observation_id": o["observation_id"],
                "status": parts[1] if len(parts) == 3 else "",
                "path": parts[2] if len(parts) == 3 else o["endpoint_template"],
                "sightings": o["observation_count"],
                "note": "response observed with no captured request (window boundary or transport filter)",
            }
        )

    return {
        "apire_protocol_spec": 1,
        "generated_utc": utcnow(),
        "generator": "apire export protocol_spec",
        "min_level": min_level,
        "transports": sorted(transports.values(), key=lambda e: -e["sightings"]),
        "hosts": hosts(endpoints),
        "endpoints": [
            {
                "method": row["method"],
                "path": row["path"],
                "host": row["host"],
                "sightings": row["sightings"],
                "statuses_observed": [r["status"] for r in row["responses"]],
                "evidence": row["evidence"],
            }
            for row in accepted_ep
        ],
        "messages": [
            {
                "transport": row["transport"],
                "channel": row["channel"],
                "direction_observed": row["direction"],
                "sightings": row["sightings"],
                "evidence": row["evidence"],
            }
            for row in accepted_ms
        ],
        "errors": errors,
        "unmatched_responses": unmatched,
        "authentication": {
            "observed": "existing application session; credential material redacted at ingestion",
            "evidence": "redaction reports are per-frame in the capture manifests",
        },
        "unknowns": "consult api_re_evidence action=unknowns for observations that resist interpretation",
        "speculative": {
            "endpoints": [{"method": r["method"], "path": r["path"], "evidence": r["evidence"]} for r in spec_ep],
            "messages": [{"channel": r["channel"], "evidence": r["evidence"]} for r in spec_ms],
        },
    }
