"""Architecture map export: processes, connections, hosts, and the
process -> host relations observed in captures."""

from __future__ import annotations

from datetime import datetime, timezone

from .. import project
from .common import DEFAULT_FLOOR, claims_by_subject, endpoint_rows, hosts as host_rows, utcnow


def architecture_document(store, capture_ids: list[str] | None = None, min_level: str = DEFAULT_FLOOR) -> dict:
    claims = claims_by_subject(store)
    endpoints = endpoint_rows(store, capture_ids, claims)
    procs = project.processes(store, capture_ids)
    conns = project.connections(store, capture_ids)

    # process -> observed sockets/connections (from per-entity frames)
    process_edges: dict[str, dict] = {}
    caps = capture_ids if capture_ids else [c["capture_id"] for c in store.list_captures()]
    for frame in store.iter_frames(caps):
        payload = frame.get("payload", {})
        if frame.get("kind_hint") != "process_meta":
            continue
        event = payload.get("event")
        if event == "socket_listening":
            entry = process_edges.setdefault(payload.get("process", ""), {"listening": [], "outbound_ports": []})
            entry["listening"].append(payload.get("local", ""))
        elif event == "connection":
            entry = process_edges.setdefault(payload.get("process", ""), {"listening": [], "outbound_ports": []})
            entry["outbound_ports"].append(payload.get("remote_port", 0))
    for entry in process_edges.values():
        entry["listening"] = sorted(set(entry["listening"]))[:20]
        entry["outbound_ports"] = sorted(set(entry["outbound_ports"]))[:20]

    return {
        "apire_architecture": 1,
        "generated_utc": utcnow(),
        "generator": "apire export architecture",
        "min_level": min_level,
        "processes": [
            {"name": p["name"], "exe": p["exe"], "pid": p["pid"], "ppid": p["ppid"]}
            for p in procs.get("processes", [])[:100]
        ],
        "module_scans": procs.get("module_scans", []),
        "process_surfaces": [{"process": k, **v} for k, v in sorted(process_edges.items()) if k],
        "connections": {
            "listening": conns.get("listening", [])[:100],
            "established": conns.get("established", [])[:100],
        },
        "hosts": host_rows(endpoints),
        "warnings": procs.get("warnings", []),
    }
