"""Normalizer v2 (host in keys), KB version notes, and the re-anchor pass."""

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pytest

import reanchor_v2  # noqa: E402
from apire.normalize import NORMALIZER_VERSION, observation_key_for_frame  # noqa: E402
from apire.store import Store  # noqa: E402

AUTH = "fixture: synthetic captures, authorized"


def _req(url: str) -> dict:
    return {"kind_hint": "http_request", "transport": "http_proxy", "payload": {"method": "GET", "url": url, "headers": {}}}


def test_http_keys_include_host():
    a = observation_key_for_frame(_req("https://one.example.com/tag"))
    b = observation_key_for_frame(_req("https://two.example.com/tag"))
    c = observation_key_for_frame(_req("https://one.example.com/tag"))
    assert a != b, "same path on different hosts must be different observations (ADR-009)"
    assert a == c


def test_kb_flags_normalizer_version_mismatch(tmp_path):
    store = Store(root=tmp_path)
    cap = store.start_capture(transport="file_ingest", authorization_statement=AUTH)
    store.append_frame(cap["capture_id"], _req("https://one.example.com/tag"))
    store.stop_capture(cap["capture_id"])
    kb_data = json.loads((tmp_path / "kb.json").read_text(encoding="utf-8"))
    assert kb_data["normalizer_version"] == NORMALIZER_VERSION

    kb_data["normalizer_version"] = 1
    (tmp_path / "kb.json").write_text(json.dumps(kb_data), encoding="utf-8")
    reloaded = Store(root=tmp_path)
    notes = reloaded.degraded_notes()
    assert notes and "normalizer v1" in notes[0] and "reanchor_v2" in notes[0]

    fresh = Store(root=tmp_path / "other")
    assert fresh.degraded_notes() == []


def test_reanchor_moves_stranded_claims(tmp_path):
    """Write a claim whose subject is a v1-era observation id (the shape a
    pre-v2 KB has), then run the migration and assert it lands on the
    current id with verification intact."""
    store = Store(root=tmp_path)
    cap = store.start_capture(transport="http_proxy", authorization_statement=AUTH)
    frame = _req("https://one.example.com/tag")
    store.append_frames(cap["capture_id"], [frame, {"kind_hint": "http_response", "transport": "http_proxy", "payload": {"path": "/tag", "status": 200, "headers": {}}}])
    store.stop_capture(cap["capture_id"])

    old_key = reanchor_v2._v1_key(frame)
    old_id = "obs_" + hashlib.sha256(old_key.encode()).hexdigest()[:16]
    new_id = "obs_" + hashlib.sha256(observation_key_for_frame(frame).encode()).hexdigest()[:16]
    assert old_id != new_id

    store.upsert_claim(
        {
            "claim_id": "clm_reanchor_test",
            "subject": old_id,
            "kind": "semantic_name",
            "value": "demo.tag.list",
            "confidence": 0.4,
            "level": "INFERRED",
            "provenance": [{"class": "captured_traffic", "artifact": old_id, "detail": "observed"}],
            "verification": {"cap_applied": 0.95, "classes": ["captured_traffic"], "verified": [], "asserted": []},
            "contradictions": [],
            "history": [],
            "note": "",
            "created_utc": "2026-09-12T00:00:00Z",
            "updated_utc": "2026-09-12T00:00:00Z",
        }
    )
    assert store.find_observation(old_id) is None, "precondition: old subject is stranded"

    result = reanchor_v2.migrate(store)
    assert not result["failed"], result
    assert any(row["claim_id"] == "clm_reanchor_test" for row in result["moved"])

    claim = next(c for c in store.all_claims() if c["claim_id"] == "clm_reanchor_test")
    assert claim["subject"] == new_id
    assert store.find_observation(new_id) is not None
    assert claim["provenance"][0]["artifact"] == new_id
    assert claim["verification"]["verified"], "the re-save passed the policy gate (recomputed)"
    assert any("re-anchored" in str(h) for h in claim["history"]) or "re-anchored" in claim["note"]


def test_reanchor_dry_run_changes_nothing(tmp_path):
    store = Store(root=tmp_path)
    cap = store.start_capture(transport="http_proxy", authorization_statement=AUTH)
    frame = _req("https://one.example.com/tag")
    store.append_frames(cap["capture_id"], [frame])
    store.stop_capture(cap["capture_id"])
    old_id = "obs_" + hashlib.sha256(reanchor_v2._v1_key(frame).encode()).hexdigest()[:16]
    store.upsert_claim(
        {
            "claim_id": "clm_dry",
            "subject": old_id,
            "kind": "semantic_name",
            "value": "demo.dry",
            "confidence": 0.0,
            "level": "UNKNOWN",
            "provenance": [{"class": "llm_proposal", "detail": "x"}],
            "verification": {"cap_applied": 0.0, "classes": ["llm_proposal"], "verified": [], "asserted": []},
            "contradictions": [],
            "history": [],
        }
    )
    result = reanchor_v2.migrate(store, dry_run=True)
    assert result["moved"]
    claim = next(c for c in store.all_claims() if c["claim_id"] == "clm_dry")
    assert claim["subject"] == old_id, "dry run must not write"
