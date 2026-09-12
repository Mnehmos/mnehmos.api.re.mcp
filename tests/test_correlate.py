"""Differential correlation: the worked example, recomputable.

Fixture: three labeled captures of an opaque application.
  A "idle"           -- heartbeat only
  B "plugin browser" -- heartbeat + type 47 sightings
  C "rename object"  -- heartbeat + type 12 sightings
The correlator must find type 47 exclusive to B, type 12 exclusive to C,
and must classify the heartbeat as periodic noise, not a signal.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from apire import correlate
from apire.errors import StoreError
from apire.store import Store

AUTH = "fixture: synthetic captures, authorized"


def _hb():
    return {"kind_hint": "ws_frame", "transport": "udp_observe", "payload": {"type": 1, "clock": True}}


def _type47(n=0):
    return {
        "kind_hint": "ws_frame",
        "transport": "udp_observe",
        "payload": {"type": 47, "plugins": ["a", "b"], "revision": n},
    }


def _type12(name="x"):
    return {"kind_hint": "ws_frame", "transport": "udp_observe", "payload": {"type": 12, "name": name}}


def _setup(tmp_path):
    store = Store(root=tmp_path)
    caps = {}
    # A: idle -- heartbeat only (regular arrivals = periodic noise)
    a = store.start_capture(transport="udp_observe", name="idle", authorization_statement=AUTH)
    for i in range(6):
        store.append_frame(a["capture_id"], _hb())
    store.stop_capture(a["capture_id"])
    store.label(a["capture_id"], label="idle")
    caps["idle"] = a["capture_id"]
    # B: plugin browser -- type 47 at *irregular* offsets (action-driven events
    # are not periodic; a fixture that interleaves them perfectly would look
    # like a heartbeat and be excluded, which is the correct behavior)
    b = store.start_capture(transport="udp_observe", name="browse", authorization_statement=AUTH)
    pattern_b = ["hb", "hb", "t47", "hb", "hb", "hb", "hb", "t47", "hb", "t47", "hb", "hb", "t47", "hb", "t47"]
    for i, what in enumerate(pattern_b):
        store.append_frame(b["capture_id"], _type47(i) if what == "t47" else _hb())
    store.stop_capture(b["capture_id"])
    store.label(b["capture_id"], label="plugin browser")
    caps["browse"] = b["capture_id"]
    # C: rename -- type 12, likewise irregular
    c = store.start_capture(transport="udp_observe", name="rename", authorization_statement=AUTH)
    pattern_c = ["hb", "t12", "hb", "hb", "t12", "hb", "hb", "hb", "t12", "hb", "t12", "hb", "t12", "hb", "hb"]
    for i, what in enumerate(pattern_c):
        store.append_frame(c["capture_id"], _type12(f"name-{i}") if what == "t12" else _hb())
    store.stop_capture(c["capture_id"])
    store.label(c["capture_id"], label="rename object")
    caps["rename"] = c["capture_id"]
    return store, caps


def test_compare_counts_per_capture(tmp_path):
    store, caps = _setup(tmp_path)
    diff = correlate.compare(store, list(caps.values()))
    assert len(diff["captures"]) == 3
    assert len(diff["rows"]) == 3, "three distinct observable behaviors (heartbeat, t47, t12)"
    for row in diff["rows"]:
        assert row["exclusive_to"] in (None, [caps["browse"]], [caps["rename"]], [caps["idle"]])


def test_candidates_are_exclusive_to_their_condition(tmp_path):
    store, caps = _setup(tmp_path)
    corr = correlate.correlate(store, list(caps.values()))
    assert corr["warning_unlabeled"] is False
    by_label = {c.get("exclusive_label"): c for c in corr["candidates"]}
    assert "plugin browser" in by_label
    assert "rename object" in by_label
    assert "idle" not in by_label, "the shared heartbeat must not be a candidate"


def test_heartbeat_is_noise_not_signal(tmp_path):
    store, caps = _setup(tmp_path)
    corr = correlate.correlate(store, list(caps.values()))
    periodic_keys = {p["canonical_key"] for p in corr["periodic_noise"]}
    assert periodic_keys, "heartbeat must be classified periodic"
    for candidate in corr["candidates"]:
        assert candidate["canonical_key"] not in periodic_keys


def test_recompute_exclusive_verifies_and_refutes(tmp_path):
    store, caps = _setup(tmp_path)
    index = store.build_observations(list(caps.values()))
    key47 = next(k for k, o in index.items() if o["observation_count"] == 5 and o["kind"] == "ws_frame" and "revision" in o["shape"])
    ok, detail = correlate.recompute_exclusive(store, list(caps.values()), key47, "plugin browser")
    assert ok, detail
    # refuted when claimed under the wrong label
    bad, why = correlate.recompute_exclusive(store, list(caps.values()), key47, "rename object")
    assert not bad and "also seen" in why
    # refuted for a key not in the cited set
    missing, why2 = correlate.recompute_exclusive(store, [caps["idle"]], key47, "plugin browser")
    assert not missing


def test_compare_needs_two_captures(tmp_path):
    store, caps = _setup(tmp_path)
    with pytest.raises(StoreError):
        correlate.compare(store, [caps["idle"]])


def test_instrument_version_mismatch_is_a_confound(tmp_path):
    """Captures from different instrument versions are not comparable: a
    signal 'exclusive' to one condition may be exclusive to the instrument."""
    store = Store(root=tmp_path)
    a = store.start_capture(transport="udp_observe", authorization_statement=AUTH, instrument="probe/v1")
    store.append_frame(a["capture_id"], _hb())
    store.stop_capture(a["capture_id"])
    store.label(a["capture_id"], label="idle")
    b = store.start_capture(transport="udp_observe", authorization_statement=AUTH, instrument="probe/v2")
    store.append_frame(b["capture_id"], _type47(1))
    store.stop_capture(b["capture_id"])
    store.label(b["capture_id"], label="browse")

    check = correlate.instrument_mismatch(store, [a["capture_id"], b["capture_id"]])
    assert check["mismatch"] is True
    assert check["distinct"] == ["probe/v1", "probe/v2"]

    c = store.start_capture(transport="udp_observe", authorization_statement=AUTH, instrument="probe/v1")
    store.append_frame(c["capture_id"], _hb())
    store.stop_capture(c["capture_id"])
    store.label(c["capture_id"], label="idle-2")
    assert correlate.instrument_mismatch(store, [a["capture_id"], c["capture_id"]])["mismatch"] is False
    # the correlation result carries the check through to the tool layer
    res = correlate.correlate(store, [a["capture_id"], b["capture_id"]])
    assert res["instrument_check"]["mismatch"] is True
