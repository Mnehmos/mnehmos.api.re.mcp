"""Projections: the evidence store viewed as protocol / architecture.

Every projection element carries its evidence level when a claim exists;
elements with no claim are reported as UNKNOWN rather than silently polished.
"""

from __future__ import annotations

from . import kb


def frame_context(store, capture_ids: list[str] | None = None) -> dict:
    """One pass over frames: per-canonical-key host, direction, ws url, URL."""
    from .normalize import observation_key_for_frame

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
    ctx = frame_context(store, caps)
    out = []
    for o in obs.values():
        if o["kind"] not in ("ws_frame", "osc_message", "pipe_message", "sse_event"):
            continue
        ctx_entry = ctx.get(o["canonical_key"], {})
        label = o["endpoint_template"] or ctx_entry.get("ws_url") or _shape_label(o["shape"])
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


def _obs_rows(store, capture_ids, kinds: set[str]) -> list[dict]:
    caps = [c["capture_id"] for c in store.list_captures() if not capture_ids or c["capture_id"] in capture_ids]
    obs = store.build_observations(caps) if caps else {}
    return [o for o in obs.values() if o["kind"] in kinds]


def events(store, capture_ids: list[str] | None = None, limit: int = 50) -> list[dict]:
    """Event-stream and lifecycle observations: SSE events and WebSocket
    open/closed/handshake frames (data frames are `messages`)."""
    rows = []
    for o in _obs_rows(store, capture_ids, {"sse_event", "ws_frame"}):
        if o["kind"] == "ws_frame" and "event" not in o["shape"]:
            continue  # data frames belong to messages
        semantic = semantic_for(store, o["observation_id"])
        rows.append(
            {
                "observation_id": o["observation_id"],
                "kind": o["kind"],
                "transport": o["transport"],
                "event": o["shape"].get("event", {}).get("constant") or o["endpoint_template"] or "(sse)",
                "channel": o["endpoint_template"] or o["shape"].get("ws_url", {}).get("constant", ""),
                "sightings": o["observation_count"],
                "captures": len(o["capture_refs"]),
                "shape": o["shape"],
                "semantic": semantic,
                "evidence_level": semantic["level"] if semantic else "OBSERVED",
            }
        )
    rows.sort(key=lambda r: -r["sightings"])
    return rows[:limit]


def schemas(store, capture_ids: list[str] | None = None, prefix: str = "", limit: int = 50) -> list[dict]:
    """The induced schema per observable behavior, with its evidence."""
    rows = []
    for o in store.build_observations(
        [c["capture_id"] for c in store.list_captures() if not capture_ids or c["capture_id"] in capture_ids]
    ).values():
        label = o["endpoint_template"] or o["observation_id"]
        if prefix and prefix not in label:
            continue
        rows.append(
            {
                "subject": o["observation_id"],
                "kind": o["kind"],
                "transport": o["transport"],
                "label": label,
                "sightings": o["observation_count"],
                "shape": o["shape"],
                "semantic": semantic_for(store, o["observation_id"]),
            }
        )
    rows.sort(key=lambda r: -r["sightings"])
    return rows[:limit]


def errors(store, capture_ids: list[str] | None = None, limit: int = 50) -> list[dict]:
    """Observed failure behavior: 4xx/5xx responses and refused CONNECTs."""
    caps = [c["capture_id"] for c in store.list_captures() if not capture_ids or c["capture_id"] in capture_ids]
    obs = store.build_observations(caps) if caps else {}
    rows = []
    for o in obs.values():
        if o["kind"] == "http_response":
            parts = o["endpoint_template"].split(" ", 2)
            status = parts[1] if len(parts) == 3 else ""
            if status.startswith(("4", "5")):
                rows.append(
                    {
                        "kind": "http_error",
                        "status": status,
                        "path": parts[2] if len(parts) == 3 else "",
                        "observation_id": o["observation_id"],
                        "sightings": o["observation_count"],
                        "body_sample": o["shape"].get("@body") or o["shape"],
                    }
                )
    for frame in store.iter_frames(caps):
        payload = frame.get("payload", {})
        if frame.get("kind_hint") == "http_request" and payload.get("refused"):
            rows.append(
                {
                    "kind": "refused",
                    "target": payload.get("url", ""),
                    "reason": payload.get("reason", ""),
                    "frame_id": frame["frame_id"],
                }
            )
    return rows[:limit]


_SERVICE_SUFFIXES = (".com", ".net", ".org", ".io", ".cloud", ".dev", ".com.br")


def _registrable(host: str) -> str:
    host = host.split(":", 1)[0].lower()
    labels = host.split(".")
    if len(labels) <= 2 or all(lbl.isdigit() for lbl in labels):
        return host  # IP addresses are their own service, not a "domain"
    return ".".join(labels[-2:])


def services(store, capture_ids: list[str] | None = None) -> list[dict]:
    """Hosts clustered into services by registrable domain, with the local
    processes observed talking to them."""
    caps = [c["capture_id"] for c in store.list_captures() if not capture_ids or c["capture_id"] in capture_ids]
    host_counts: dict[str, int] = {}
    for frame in store.iter_frames(caps):
        payload = frame.get("payload", {})
        if payload.get("url") and frame.get("kind_hint") in ("http_request", "http_response"):
            tail = payload["url"].split("//", 1)[-1]
            host = tail.split("/", 1)[0]
            host_counts[host] = host_counts.get(host, 0) + 1
    process_hosts: dict[str, set] = {}
    for frame in store.iter_frames(caps):
        payload = frame.get("payload", {})
        if frame.get("kind_hint") == "process_meta" and payload.get("event") == "connection":
            remote = str(payload.get("remote", ""))
            if remote:
                process_hosts.setdefault(_registrable(remote), set()).add(payload.get("process", ""))

    grouped: dict[str, dict] = {}
    for host, count in host_counts.items():
        svc = grouped.setdefault(_registrable(host), {"service": _registrable(host), "hosts": {}, "requests": 0, "processes": []})
        svc["hosts"][host] = count
        svc["requests"] += count
    # hosts seen only through process connections still belong in the map
    for name in process_hosts:
        grouped.setdefault(name, {"service": name, "hosts": {}, "requests": 0, "processes": []})
    for name, svc in grouped.items():
        svc["processes"] = sorted(p for p in process_hosts.get(name, set()) if p)
    return sorted(grouped.values(), key=lambda s: -s["requests"])


def _boundary_of(host: str) -> str:
    host = host.split(":", 1)[0].lower()
    if host in ("localhost", "127.0.0.1", "::1") or host.startswith("127."):
        return "loopback"
    if host.startswith(("10.", "192.168.", "169.254.")) or any(host.startswith(f"172.{n}.") for n in range(16, 32)):
        return "local_network"
    return "public_internet"


def boundaries(store, capture_ids: list[str] | None = None) -> list[dict]:
    """Trust boundaries crossed by observed traffic: loopback, local
    network, public internet — with the hosts and processes on each side."""
    caps = [c["capture_id"] for c in store.list_captures() if not capture_ids or c["capture_id"] in capture_ids]
    out: dict[str, dict] = {}
    for frame in store.iter_frames(caps):
        payload = frame.get("payload", {})
        host = ""
        if payload.get("url"):
            host = payload["url"].split("//", 1)[-1].split("/", 1)[0]
        elif frame.get("kind_hint") == "process_meta" and payload.get("event") == "connection":
            host = str(payload.get("remote", ""))
        elif frame.get("kind_hint") == "process_meta" and payload.get("event") == "socket_listening":
            host = str(payload.get("local", ""))
        if not host:
            continue
        b = _boundary_of(host)
        entry = out.setdefault(b, {"boundary": b, "hosts": {}, "sightings": 0, "processes": set()})
        entry["hosts"][host] = entry["hosts"].get(host, 0) + 1
        entry["sightings"] += 1
        if payload.get("process"):
            entry["processes"].add(payload["process"])
    rows = []
    for entry in out.values():
        entry["processes"] = sorted(entry["processes"])[:20]
        entry["hosts"] = dict(sorted(entry["hosts"].items(), key=lambda kv: -kv[1])[:20])
        rows.append(entry)
    return sorted(rows, key=lambda e: -e["sightings"])
