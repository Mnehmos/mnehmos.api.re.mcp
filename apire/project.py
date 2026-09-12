"""Projections: the evidence store viewed as protocol / architecture.

Every projection element carries its evidence level when a claim exists;
elements with no claim are reported as UNKNOWN rather than silently polished.
"""

from __future__ import annotations

from . import kb


def semantic_for(store, observation_id: str) -> dict | None:
    claims = [c for c in kb.query(store, subject=observation_id) if c["kind"] == "semantic_name"]
    if not claims:
        return None
    best = max(claims, key=lambda c: c["confidence"])
    return {"name": best["value"], "level": best["level"], "confidence": best["confidence"], "claim_id": best["claim_id"]}


def transports_seen(store, capture_ids: list[str] | None = None) -> list[dict]:
    caps = [c for c in store.list_captures() if not capture_ids or c["capture_id"] in capture_ids]
    ids = [c["capture_id"] for c in caps]
    obs = store.build_observations(ids) if ids else {}
    per: dict[str, dict] = {}
    for o in obs.values():
        entry = per.setdefault(o["transport"], {"transport": o["transport"], "kinds": set(), "observations": 0, "sightings": 0})
        entry["kinds"].add(o["kind"])
        entry["observations"] += 1
        entry["sightings"] += o["observation_count"]
    out = []
    for entry in per.values():
        entry["kinds"] = sorted(entry["kinds"])
        entry["captures"] = sum(1 for c in caps if c["transport"] == entry["transport"])
        out.append(entry)
    out.sort(key=lambda e: -e["sightings"])
    return out


def endpoints(store, capture_ids: list[str] | None = None, prefix: str = "") -> list[dict]:
    caps = [c["capture_id"] for c in store.list_captures() if not capture_ids or c["capture_id"] in capture_ids]
    obs = store.build_observations(caps) if caps else {}
    requests = {o["endpoint_template"]: o for o in obs.values() if o["kind"] == "http_request"}
    statuses: dict[str, set] = {}
    for o in obs.values():
        if o["kind"] == "http_response":
            statuses.setdefault(o["endpoint_template"], set()).update(
                str(s.get("status", "")) for s in [o["shape"].get("status", {})]
            )
    out = []
    for template, o in sorted(requests.items()):
        if prefix and prefix not in template:
            continue
        path = template.split(" ", 1)[1] if " " in template else template
        out.append(
            {
                "endpoint": template,
                "observation_id": o["observation_id"],
                "sightings": o["observation_count"],
                "captures": len(o["capture_refs"]),
                "statuses_observed": sorted(str(x) for x in statuses.get(path, set())),
                "semantic": semantic_for(store, o["observation_id"]),
            }
        )
    out.sort(key=lambda e: -e["sightings"])
    return out


def messages(store, capture_ids: list[str] | None = None, prefix: str = "") -> list[dict]:
    caps = [c["capture_id"] for c in store.list_captures() if not capture_ids or c["capture_id"] in capture_ids]
    obs = store.build_observations(caps) if caps else {}
    out = []
    for o in obs.values():
        if o["kind"] not in ("ws_frame", "osc_message", "pipe_message", "sse_event"):
            continue
        label = o["endpoint_template"] or _shape_label(o["shape"])
        if prefix and prefix not in label:
            continue
        semantic = semantic_for(store, o["observation_id"])
        out.append(
            {
                "message": label,
                "transport": o["transport"],
                "observation_id": o["observation_id"],
                "sightings": o["observation_count"],
                "captures": len(o["capture_refs"]),
                "shape": o["shape"],
                "semantic": semantic,
                "evidence_level": semantic["level"] if semantic else "UNKNOWN",
            }
        )
    out.sort(key=lambda m: -m["sightings"])
    return out


def _shape_label(shape: dict) -> str:
    consts = {k: v.get("constant") for k, v in shape.items() if "constant" in v}
    if consts:
        return "{" + ", ".join(f"{k}={v}" for k, v in sorted(consts.items())[:4]) + "}"
    return "{" + ", ".join(sorted(shape)[:4]) + "}"


def _meta_frames(store, capture_ids: list[str] | None, events: set[str]) -> list[dict]:
    caps = [c["capture_id"] for c in store.list_captures() if not capture_ids or c["capture_id"] in capture_ids]
    out = []
    for frame in store.iter_frames(caps):
        payload = frame.get("payload", {})
        if frame.get("kind_hint") == "process_meta" and payload.get("event") in events:
            out.append(frame)
    return out


def processes(store, capture_ids: list[str] | None = None, hint: str = "") -> dict:
    inventories = _meta_frames(store, capture_ids, {"process_inventory"})
    scans = _meta_frames(store, capture_ids, {"module_scan", "listening_sockets_warning"})
    procs = []
    if inventories:
        procs = inventories[-1]["payload"].get("processes", [])
    if hint:
        needle = hint.lower()
        procs = [p for p in procs if needle in (p["name"] or "").lower() or needle in (p["exe"] or "").lower()]
    return {
        "process_count": len(inventories[-1]["payload"].get("processes", [])) if inventories else 0,
        "matching": len(procs),
        "processes": procs[:200],
        "module_scans": [f["payload"] for f in scans if f["payload"].get("event") == "module_scan"][-12:],
        "warnings": [f["payload"]["detail"] for f in scans if f["payload"].get("event") == "listening_sockets_warning"],
    }


def connections(store, capture_ids: list[str] | None = None) -> dict:
    """Established and listening inet connections as per-entity frames."""
    caps = [c["capture_id"] for c in store.list_captures() if not capture_ids or c["capture_id"] in capture_ids]
    listening, established = [], []
    for frame in store.iter_frames(caps):
        payload = frame.get("payload", {})
        if frame.get("kind_hint") != "process_meta":
            continue
        event = payload.get("event")
        if event == "socket_listening":
            listening.append({k: payload.get(k) for k in ("proto", "local", "pid", "process")})
        elif event == "connection":
            established.append({k: payload.get(k) for k in ("proto", "local_port", "remote", "remote_port", "pid", "process")})
    return {"listening_count": len(listening), "established_count": len(established), "listening": listening[:300], "established": established[:300]}
