"""AsyncAPI 2.6 export: observed asynchronous surfaces (WS, OSC, pipes, SSE).

Direction is recorded as observed (server_to_client / client_to_server); the
publish/subscribe framing of AsyncAPI is documented in x-apire, because the
observed application's role is not assumed.
"""

from __future__ import annotations

from .common import DEFAULT_FLOOR, claims_by_subject, message_rows, shape_to_schema, split_by_floor, utcnow


def asyncapi_document(store, capture_ids: list[str] | None = None, min_level: str = DEFAULT_FLOOR) -> dict:
    claims = claims_by_subject(store)
    rows = message_rows(store, capture_ids, claims)
    accepted, speculative = split_by_floor(rows, min_level)

    channels: dict[str, dict] = {}
    for row in accepted:
        channel = row["channel"]
        direction = row["direction"] or "unspecified"
        # AsyncAPI 2.x: publish = the provider sends to subscribers,
        # subscribe = the provider receives. Observed server->client traffic
        # is the provider publishing; client->server is the provider receiving.
        op = "publish" if direction == "server_to_client" else "subscribe"
        message = {
            "name": row["evidence"].get("semantic") or row["observation_id"],
            "title": row["evidence"].get("semantic") or row["channel"],
            "payload": shape_to_schema(row["shape"]),
            "x-apire": {
                **row["evidence"],
                "observation_id": row["observation_id"],
                "sightings": row["sightings"],
                "direction_observed": direction,
                "transport": row["transport"],
            },
        }
        entry = channels.setdefault(channel, {})
        entry.setdefault(op, {"message": message})

    return {
        "asyncapi": "2.6.0",
        "info": {
            "title": "Observed asynchronous surface",
            "version": "0.0.0-observed",
            "description": (
                "Reconstructed from passive observation by apire. Channel names are the "
                "observed addresses/URLs; payload schemas are induced from captured frames. "
                "Direction is what was observed, recorded in x-apire."
            ),
        },
        "channels": channels,
        "x-apire": {
            "generated_utc": utcnow(),
            "generator": "apire export asyncapi",
            "min_level": min_level,
            "speculative": [
                {"channel": r["channel"], "transport": r["transport"], "evidence": r["evidence"]} for r in speculative
            ],
        },
    }
