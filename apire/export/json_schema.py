"""JSON Schema export: one definition per observable behavior (canonical key)."""

from __future__ import annotations

from .common import DEFAULT_FLOOR, claims_by_subject, endpoint_rows, message_rows, shape_to_schema, slug, split_by_floor, utcnow


def json_schema_document(store, capture_ids: list[str] | None = None, min_level: str = DEFAULT_FLOOR) -> dict:
    claims = claims_by_subject(store)
    rows = endpoint_rows(store, capture_ids, claims) + message_rows(store, capture_ids, claims)
    accepted, speculative = split_by_floor(rows, min_level)

    defs: dict[str, dict] = {}
    for row in accepted:
        name = row["evidence"].get("semantic") or (
            f"{row.get('method', 'msg')}_{row.get('path') or row.get('channel', '')}"
        )
        key = slug(str(name))
        base = key
        n = 2
        while key in defs:
            key = f"{base}_{n}"
            n += 1
        defs[key] = {
            "title": row["evidence"].get("semantic") or key,
            "description": (
                f"induced from {row['sightings']} sighting(s) in "
                f"{', '.join(row['evidence']['captures'])}"
            ),
            **shape_to_schema(row["shape"]),
            "x-apire": {**row["evidence"], "observation_id": row["observation_id"]},
        }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "apire:observed",
        "title": "Observed payload schemas",
        "$defs": defs,
        "x-apire": {
            "generated_utc": utcnow(),
            "generator": "apire export json_schema",
            "min_level": min_level,
            "speculative": [
                {"observation_id": r["observation_id"], "evidence": r["evidence"]} for r in speculative
            ],
        },
    }
