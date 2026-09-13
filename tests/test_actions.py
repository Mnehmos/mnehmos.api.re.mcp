"""The six previously-refused actions: protocol events/schemas/errors,
architecture services/boundaries, evidence experiments."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from apire import experiments, project, semantics
from apire.store import Store

AUTH = "fixture: synthetic captures, authorized"


@pytest.fixture()
def rig(tmp_path):
    store = Store(root=tmp_path)
    cap = store.start_capture(transport="devtools_attach", authorization_statement=AUTH)
    cid = cap["capture_id"]
    frames = [
        # WS lifecycle + data frame
        {"kind_hint": "ws_frame", "transport": "devtools_attach", "payload": {"event": "open", "ws_url": "wss://events.example.com/ws"}},
        {"kind_hint": "ws_frame", "transport": "devtools_attach", "payload": {"opcode": 1, "payloadData": '{"n":1}', "ws_url": "wss://events.example.com/ws"}},
        {"kind_hint": "ws_frame", "transport": "devtools_attach", "payload": {"event": "closed", "ws_url": "wss://events.example.com/ws"}},
        # SSE event
        {"kind_hint": "sse_event", "transport": "http_proxy", "payload": {"path": "/stream", "url": "http://127.0.0.1:9001/stream", "event": "tick", "data": '{"n":1}'}},
        # errors: 404 + refused CONNECT
        {"kind_hint": "http_response", "transport": "http_proxy", "payload": {"path": "/api/missing", "status": 404, "headers": {}}},
        {"kind_hint": "http_request", "transport": "http_proxy", "payload": {"method": "CONNECT", "url": "x:443", "refused": True, "reason": "opaque tunnel"}},
        # a normal request/response for schemas
        {"kind_hint": "http_request", "transport": "http_proxy", "payload": {"method": "GET", "url": "https://api.example.com/api/items?page=1", "headers": {}}},
        {"kind_hint": "http_response", "transport": "http_proxy", "payload": {"path": "/api/items", "status": 200, "headers": {}, "body_sample": '{"items":[{"id":1}]}'}},
        # process/connection metadata: loopback + public hosts
        {"kind_hint": "process_meta", "transport": "process_meta", "payload": {"event": "process_inventory", "count": 1, "processes": [{"pid": 7, "ppid": 1, "name": "fl64.exe", "exe": "F:/FL64.exe"}]}},
        {"kind_hint": "process_meta", "transport": "process_meta", "payload": {"event": "socket_listening", "proto": "tcp", "local": "127.0.0.1:9222", "pid": 7, "process": "fl64.exe"}},
        {"kind_hint": "process_meta", "transport": "process_meta", "payload": {"event": "connection", "proto": "tcp", "local_port": 51000, "remote": "1.2.3.4:443", "remote_port": 443, "pid": 7, "process": "fl64.exe"}},
        {"kind_hint": "process_meta", "transport": "process_meta", "payload": {"event": "connection", "proto": "tcp", "local_port": 51001, "remote": "172.217.0.1:443", "remote_port": 443, "pid": 7, "process": "fl64.exe"}},
    ]
    store.append_frames(cid, frames)
    store.stop_capture(cid)
    return store, cid


def test_protocol_events_splits_lifecycle_from_messages(rig):
    store, cid = rig
    events = project.events(store, [cid])
    event_names = {e["event"] for e in events}
    assert {"open", "closed", "tick"} <= event_names
    messages = project.messages(store, [cid])
    assert any(m["message"] == "wss://events.example.com/ws" for m in messages), "data frames stay in messages"


def test_protocol_schemas_carry_shapes(rig):
    store, cid = rig
    rows = project.schemas(store, [cid])
    items = next(r for r in rows if "items" in r["label"] or "items" in str(r["shape"]))
    assert items["shape"], "induced shape present"
    assert items["sightings"] >= 1


def test_protocol_errors_lists_4xx_and_refusals(rig):
    store, cid = rig
    rows = project.errors(store, [cid])
    assert any(r.get("status") == "404" for r in rows)
    assert any(r.get("kind") == "refused" and "opaque" in r.get("reason", "") for r in rows)


def test_architecture_services_group_by_registrable_domain(rig):
    store, cid = rig
    rows = project.services(store, [cid])
    names = {r["service"] for r in rows}
    assert "example.com" in names
    assert any(r["service"] == "example.com" and "api.example.com" in r["hosts"] for r in rows)
    # IPs stay whole and carry their local process
    assert any(r["service"] == "172.217.0.1" and "fl64.exe" in r["processes"] for r in rows)


def test_architecture_boundaries_classify(rig):
    store, cid = rig
    rows = project.boundaries(store, [cid])
    kinds = {r["boundary"] for r in rows}
    assert "loopback" in kinds and "public_internet" in kinds


def test_experiments_propose_deterministic_next_observations(rig):
    store, cid = rig
    obs = store.build_observations([cid])
    target = next(o for o in obs.values() if o["kind"] == "http_request" and "items" in o["endpoint_template"])
    claim = semantics.propose(store, target["observation_id"], "demo.items.list", "listing endpoint", [])
    rows = experiments.propose(store)
    kinds = {r["kind"] for r in rows}
    assert "raise_claim" in kinds, "a below-threshold claim must yield a raising experiment"
    assert "interpret_unknown" in kinds
    raise_row = next(r for r in rows if r["kind"] == "raise_claim")
    assert claim["claim_id"] in raise_row["evidence_refs"]
    assert raise_row["experiment"], "proposals state the action to perform"
    # subject filter narrows to the cited items
    scoped = experiments.propose(store, target["observation_id"])
    assert all(target["observation_id"] in r["evidence_refs"] for r in scoped)
