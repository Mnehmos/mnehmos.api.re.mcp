"""OpenAPI 3.1 export: observed HTTP behavior as a document.

Honesty rules: every operation carries an `x-apire` evidence block; the
property types come from induced shapes, not from guesses; responses are the
statuses actually seen. Operations whose evidence sits below the floor move
to `x-apire.speculative` instead of posing as observed fact.
"""

from __future__ import annotations

from .common import DEFAULT_FLOOR, endpoint_rows, hosts, shape_to_schema, split_by_floor, utcnow


def _path_parameters(path: str) -> tuple[str, list[dict]]:
    """`/a/{var}/b/{var}` -> `/a/{p1}/b/{p2}` with OpenAPI parameter list
    (duplicate template names would make the path invalid)."""
    parts = []
    params = []
    n = 0
    for segment in path.split("/"):
        if segment == "{var}":
            n += 1
            name = f"p{n}"
            params.append({"name": name, "in": "path", "required": True, "schema": {"type": "string"}})
            parts.append("{" + name + "}")
        else:
            parts.append(segment)
    return "/".join(parts), params


def openapi_document(store, capture_ids: list[str] | None = None, min_level: str = DEFAULT_FLOOR) -> dict:
    from .common import claims_by_subject

    claims = claims_by_subject(store)
    rows = endpoint_rows(store, capture_ids, claims)
    accepted, speculative = split_by_floor(rows, min_level)
    host_list = hosts(rows)

    paths: dict[str, dict] = {}
    for row in accepted:
        path_key, params = _path_parameters(row["path"])
        operation: dict = {
            "operationId": (row["evidence"].get("semantic") or f"{row['method'].lower()}_{_path_slug(row['path'])}"),
            "summary": row["evidence"].get("semantic") or f"observed {row['method']} {row['path']}",
            "parameters": params,
            "responses": {},
            "x-apire": {
                **row["evidence"],
                "observation_id": row["observation_id"],
                "sightings": row["sightings"],
                "request_shape": row["shape"],
            },
        }
        if row["responses"]:
            for resp in row["responses"]:
                entry: dict = {
                    "description": f"observed {resp['status']}",
                    "x-apire": {"observation_id": resp["observation_id"]},
                }
                body_shape = {k: v for k, v in (resp.get("shape") or {}).items() if k != "status"}
                if body_shape:
                    entry["content"] = {"application/json": {"schema": shape_to_schema(body_shape)}}
                operation["responses"][resp["status"]] = entry
        else:
            operation["responses"]["default"] = {"description": "no response observed in the captured window"}
        paths.setdefault(path_key, {})[row["method"].lower()] = operation

    doc = {
        "openapi": "3.1.0",
        "info": {
            "title": f"Observed API — {host_list[0]['host'] if host_list else 'target'}",
            "version": "0.0.0-observed",
            "description": (
                "Reconstructed from passive observation by apire. Every operation carries an "
                "x-apire evidence block (level, confidence, citing captures, claim id). "
                "Types are induced from observed payload shapes. Authentication: existing "
                "application session; credential material was redacted at ingestion."
            ),
        },
        "servers": [{"url": f"https://{h['host']}"} for h in host_list if h["host"] != "(unknown)"][:5],
        "paths": paths,
        "x-apire": {
            "generated_utc": utcnow(),
            "generator": "apire export openapi",
            "min_level": min_level,
            "hosts": host_list,
            "speculative": [
                {
                    "method": row["method"],
                    "path": row["path"],
                    "evidence": row["evidence"],
                    "reason": f"evidence level {row['evidence']['level']} is below the {min_level} floor",
                }
                for row in speculative
            ],
        },
    }
    return doc


def _path_slug(path: str) -> str:
    return path.strip("/").replace("{var}", "by_id").replace("/", "_") or "root"
