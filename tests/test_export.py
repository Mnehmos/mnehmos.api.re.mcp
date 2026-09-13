"""Exporters: six formats, evidence on every element, floors enforced,
specs parse, and no credential material ever appears in a document."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from apire import kb, semantics
from apire.export import (
    architecture_document,
    asyncapi_document,
    json_schema_document,
    mcp_candidate_document,
    openapi_document,
    protocol_spec_document,
)
from apire.store import Store

AUTH = "fixture: synthetic captures, authorized"
SECRET = "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJl"


@pytest.fixture()
def rig(tmp_path):
    store = Store(root=tmp_path)
    cap = store.start_capture(transport="file_ingest", authorization_statement=AUTH)
    cid = cap["capture_id"]
    # HTTP: one endpoint twice (one numeric-id variant), responses 200 + 404,
    # credential header that must never appear in an export.
    for _ in range(2):
        store.append_frame(
            cid,
            {
                "kind_hint": "http_request",
                "transport": "http_proxy",
                "payload": {
                    "method": "GET",
                    "url": "https://api.example.com/api/projects",
                    "headers": {"Authorization": SECRET, "Accept": "application/json"},
                },
            },
        )
    store.append_frame(
        cid,
        {
            "kind_hint": "http_request",
            "transport": "http_proxy",
            "payload": {"method": "GET", "url": "https://api.example.com/api/projects/123", "headers": {}},
        },
    )
    store.append_frame(
        cid,
        {
            "kind_hint": "http_response",
            "transport": "http_proxy",
            "payload": {"path": "/api/projects", "status": 200, "headers": {"content-type": "application/json"}, "mimeType": "application/json"},
        },
    )
    store.append_frame(
        cid,
        {
            "kind_hint": "http_response",
            "transport": "http_proxy",
            "payload": {"path": "/api/missing", "status": 404, "headers": {"content-type": "application/json"}, "mimeType": "application/json"},
        },
    )
    # asynchronous surface
    store.append_frame(
        cid,
        {
            "kind_hint": "osc_message",
            "transport": "udp_observe",
            "direction": "server_to_client",
            "payload": {"address": "/mixer/volume", "types": ",f", "args": [0.5]},
        },
    )
    store.append_frame(
        cid,
        {
            "kind_hint": "ws_frame",
            "transport": "devtools_attach",
            "direction": "server_to_client",
            "payload": {"opcode": 1, "payloadData": '{"type":7,"load":0.5}', "ws_url": "wss://api.example.com/events"},
        },
    )
    # process metadata for the architecture map
    store.append_frame(
        cid,
        {
            "kind_hint": "process_meta",
            "transport": "process_meta",
            "payload": {
                "event": "process_inventory",
                "count": 1,
                "processes": [{"pid": 42, "ppid": 1, "name": "fl64.exe", "exe": r"F:\FL Studio\FL64.exe"}],
            },
        },
    )
    store.append_frame(
        cid,
        {
            "kind_hint": "process_meta",
            "transport": "process_meta",
            "payload": {"event": "socket_listening", "proto": "tcp", "local": "127.0.0.1:9222", "pid": 42, "process": "fl64.exe"},
        },
    )
    store.append_frame(
        cid,
        {
            "kind_hint": "process_meta",
            "transport": "process_meta",
            "payload": {"event": "connection", "proto": "tcp", "local_port": 51000, "remote": "1.2.3.4:443", "remote_port": 443, "pid": 42, "process": "fl64.exe"},
        },
    )
    store.stop_capture(cid)
    store.label(cid, label="browse")

    obs = store.build_observations([cid])
    projects_obs = next(o for o in obs.values() if o["endpoint_template"] == "GET /api/projects")
    unknown_obs = next(o for o in obs.values() if o["endpoint_template"] == "GET /api/projects/{var}")

    # claimed endpoint at INFERRED (proposal + verified captured_traffic)
    claim = semantics.propose(store, projects_obs["observation_id"], "demo.projects.list", "listing endpoint", [])
    kb.save_claim(
        store,
        subject=claim["subject"],
        kind="semantic_name",
        value="demo.projects.list",
        confidence=0.40,
        provenance=[{"class": "captured_traffic", "artifact": claim["subject"], "detail": "observed 2x"}],
        claim_id=claim["claim_id"],
    )
    # unclaimed endpoint gets a bare proposal only -> UNKNOWN -> speculative
    semantics.propose(store, unknown_obs["observation_id"], "demo.projects.get", "detail read", [])
    return store, cid, projects_obs["observation_id"], unknown_obs["observation_id"]


def test_openapi_has_paths_evidence_and_no_secrets(rig):
    store, cid, _, _ = rig
    doc = openapi_document(store, [cid])
    assert doc["openapi"] == "3.1.0"
    assert "/api/projects" in doc["paths"]
    op = doc["paths"]["/api/projects"]["get"]
    assert op["operationId"] == "demo.projects.list"
    assert op["x-apire"]["level"] == "INFERRED"
    assert op["x-apire"]["confidence"] == 0.40
    assert "200" in op["responses"]
    # the low-confidence endpoint is speculative, not posing as observed fact
    assert any(s["path"] == "/api/projects/{var}" for s in doc["x-apire"]["speculative"])
    assert "/api/projects/{p1}" not in doc["paths"], "speculative endpoint must not appear as an observed path"
    assert SECRET not in json.dumps(doc)
    assert "eyJhbGciOiJIUzI1NiJ9" not in json.dumps(doc)


def test_path_templating_numbers_duplicate_vars():
    from apire.export.openapi import _path_parameters

    path, params = _path_parameters("/api/{var}/tracks/{var}/notes")
    assert path == "/api/{p1}/tracks/{p2}/notes"
    assert [p["name"] for p in params] == ["p1", "p2"]


def test_openapi_floor_moves_everything_to_speculative(rig):
    store, cid, _, _ = rig
    doc = openapi_document(store, [cid], min_level="CONFIRMED")
    assert doc["paths"] == {}
    assert doc["x-apire"]["speculative"], "nothing reached CONFIRMED; everything must be speculative"


def test_asyncapi_channels_from_observed_addresses(rig):
    store, cid, _, _ = rig
    doc = asyncapi_document(store, [cid])
    assert doc["asyncapi"] == "2.6.0"
    assert "/mixer/volume" in doc["channels"]
    assert "wss://api.example.com/events" in doc["channels"]
    ws = doc["channels"]["wss://api.example.com/events"]["publish"]["message"]
    assert ws["x-apire"]["direction_observed"] == "server_to_client"
    assert ws["payload"]["type"] == "object"


def test_json_schema_defs_are_parsable_and_typed(rig):
    store, cid, _, _ = rig
    doc = json_schema_document(store, [cid])
    assert doc["$schema"].endswith("2020-12/schema")
    assert doc["$defs"], "no schema definitions emitted"
    demo = next(v for k, v in doc["$defs"].items() if k.startswith("demo_projects_list"))
    assert demo["type"] == "object"
    assert demo["properties"]["method"]["const"] == "GET"
    json.dumps(doc)  # serializable


def test_protocol_spec_catalogs_transports_errors_and_auth(rig):
    store, cid, _, _ = rig
    doc = protocol_spec_document(store, [cid])
    transports = {t["transport"] for t in doc["transports"]}
    assert {"http_proxy", "udp_observe", "devtools_attach"} <= transports | {"process_meta"}
    # the fixture's 404 has no captured request: it belongs in the honest
    # unmatched section, not silently dropped and not faked as a matched error
    assert any(u["status"] == "404" for u in doc["unmatched_responses"])
    assert "redacted at ingestion" in doc["authentication"]["observed"]
    assert any(e["path"] == "/api/projects" for e in doc["endpoints"])


def test_architecture_maps_processes_and_surfaces(rig):
    store, cid, _, _ = rig
    doc = architecture_document(store, [cid])
    assert any(p["name"] == "fl64.exe" for p in doc["processes"])
    surface = next(s for s in doc["process_surfaces"] if s["process"] == "fl64.exe")
    assert "127.0.0.1:9222" in surface["listening"]
    assert 443 in surface["outbound_ports"]
    assert any(h["host"] == "api.example.com" for h in doc["hosts"])


def test_mcp_candidate_groups_capabilities_without_transport(rig):
    store, cid, _, _ = rig
    doc = mcp_candidate_document(store, [cid])
    assert doc["apire_mcp_candidate"] == 1
    tool = next(t for t in doc["candidate_tools"] if t["name"] == "demo_projects")
    actions = {a["action"] for a in tool["actions"]}
    assert "list" in actions
    assert tool["best_level"] == "INFERRED"
    # it specifies a surface; it must not contain a way to call one
    text = json.dumps(doc).lower()
    assert "no transport" in text or "implements none" in text
    for forbidden in ('"send"', '"replay"', '"execute"'):
        assert forbidden not in text


def test_mcp_candidate_dedupes_same_action_across_shapes(tmp_path):
    """One endpoint can appear under several canonical keys (different query
    shapes); the candidate surface must merge them into one action that keeps
    every observation id."""
    store = Store(root=tmp_path)
    cap = store.start_capture(transport="file_ingest", authorization_statement=AUTH)
    cid = cap["capture_id"]
    for url in (
        "https://api.example.com/g/collect?v=2&en=page_view",
        "https://api.example.com/g/collect?v=2&en=click&ep=1",
    ):
        store.append_frame(
            cid,
            {"kind_hint": "http_request", "transport": "http_proxy", "payload": {"method": "POST", "url": url, "headers": {}}},
        )
    store.stop_capture(cid)
    doc = mcp_candidate_document(store, [cid])
    tool = next(t for t in doc["candidate_tools"] if t["name"] == "api_example_com")
    collects = [a for a in tool["actions"] if a["action"] == "post_collect"]
    assert len(collects) == 1, "same endpoint must be one action"
    assert len(collects[0]["observation_ids"]) == 2
    assert collects[0]["sightings"] == 2


def test_all_exporters_survive_empty_store(tmp_path):
    empty = Store(root=tmp_path)
    for exporter in (openapi_document, asyncapi_document, json_schema_document, protocol_spec_document, architecture_document, mcp_candidate_document):
        doc = exporter(empty, None)
        assert json.dumps(doc)  # serializable, no crash on nothing observed
