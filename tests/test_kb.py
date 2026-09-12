"""The evidence policy is law: caps, corroboration, recomputation.

These tests pin the refusals. A claim that cannot re-derive from captured
evidence does not reach the store, and the model's word is worth exactly
zero on its own.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from apire import correlate, kb, semantics
from apire.errors import PolicyError
from apire.store import Store

AUTH = "fixture: synthetic captures, authorized"


def _hb():
    return {"kind_hint": "ws_frame", "transport": "udp_observe", "payload": {"type": 1, "clock": True}}


def _type47(n=0):
    return {"kind_hint": "ws_frame", "transport": "udp_observe", "payload": {"type": 47, "plugins": ["a"], "revision": n}}


@pytest.fixture()
def rig(tmp_path):
    """Two labeled captures: idle vs plugin browser; type 47 exclusive to
    browse and irregular (action-driven, not heartbeat)."""
    store = Store(root=tmp_path)
    a = store.start_capture(transport="udp_observe", name="idle", authorization_statement=AUTH)
    for _ in range(4):
        store.append_frame(a["capture_id"], _hb())
    store.stop_capture(a["capture_id"])
    store.label(a["capture_id"], label="idle")
    b = store.start_capture(transport="udp_observe", name="browse", authorization_statement=AUTH)
    pattern = ["hb", "hb", "t47", "hb", "hb", "hb", "t47", "hb", "hb", "t47", "hb", "t47", "hb", "t47", "hb"]
    for i, what in enumerate(pattern):
        store.append_frame(b["capture_id"], _type47(i) if what == "t47" else _hb())
    store.stop_capture(b["capture_id"])
    store.label(b["capture_id"], label="plugin browser")
    caps = [a["capture_id"], b["capture_id"]]
    obs = store.build_observations(caps)
    key47 = next(k for k, o in obs.items() if "revision" in o["shape"] and o["observation_count"] == 5)
    return store, caps, obs[key47], key47


def test_llm_proposal_cannot_exceed_zero_confidence(rig):
    store, caps, obs, key = rig
    with pytest.raises(PolicyError) as err:
        kb.save_claim(
            store,
            subject=obs["observation_id"],
            kind="semantic_name",
            value="plugin.catalog.updated",
            confidence=0.5,
            provenance=[{"class": "llm_proposal", "detail": "looks like a plugin catalog"}],
        )
    assert err.value.context["cap"] == 0.0


def test_high_confidence_needs_two_distinct_classes(rig):
    store, caps, obs, key = rig
    with pytest.raises(PolicyError) as err:
        kb.save_claim(
            store,
            subject=obs["observation_id"],
            kind="semantic_name",
            value="plugin.catalog.updated",
            confidence=0.78,
            provenance=[
                {
                    "class": "differential_exclusive",
                    "artifact": "captures:" + ",".join(caps),
                    "capture_ids": caps,
                    "canonical_key": key,
                    "label": "plugin browser",
                }
            ],
        )
    assert "distinct provenance classes" in err.value.message


def test_failed_recomputation_rejects_the_write(rig):
    store, caps, obs, key = rig
    with pytest.raises(PolicyError) as err:
        kb.save_claim(
            store,
            subject=obs["observation_id"],
            kind="semantic_name",
            value="plugin.catalog.updated",
            confidence=0.60,
            provenance=[
                {"class": "captured_traffic", "artifact": obs["observation_id"]},
                {
                    "class": "differential_exclusive",
                    "artifact": "captures:" + ",".join(caps),
                    "capture_ids": caps,
                    "canonical_key": key,
                    "label": "rename object",  # wrong label: refuted by recomputation
                },
            ],
        )
    assert err.value.context["provenance_class"] == "differential_exclusive"


def test_verified_claim_is_stored_with_its_verification_record(rig):
    store, caps, obs, key = rig
    claim = kb.save_claim(
        store,
        subject=obs["observation_id"],
        kind="semantic_name",
        value="plugin.catalog.updated",
        confidence=0.78,
        provenance=[
            {"class": "captured_traffic", "artifact": obs["observation_id"], "detail": "seen in captures"},
            {
                "class": "differential_exclusive",
                "artifact": "captures:" + ",".join(caps),
                "capture_ids": caps,
                "canonical_key": key,
                "label": "plugin browser",
            },
        ],
        note="proposed by model; raised by differential evidence",
    )
    assert claim["level"] == "STRONGLY_INFERRED"
    assert claim["confidence"] == 0.78
    verified_classes = {v["class"] for v in claim["verification"]["verified"]}
    assert verified_classes == {"captured_traffic", "differential_exclusive"}
    assert "5/5" in next(v["detail"] for v in claim["verification"]["verified"] if v["class"] == "differential_exclusive")


def test_revision_is_history_not_rewrite(rig):
    store, caps, obs, key = rig
    c1 = kb.save_claim(
        store, obs["observation_id"], "semantic_name", "plugin.catalog.updated", 0.0,
        [{"class": "llm_proposal", "detail": "guess"}],
    )
    c2 = kb.save_claim(
        store, obs["observation_id"], "semantic_name", "plugin.catalog.updated", 0.60,
        [
            {"class": "captured_traffic", "artifact": obs["observation_id"]},
            {"class": "differential_exclusive", "artifact": "c:" + ",".join(caps), "capture_ids": caps, "canonical_key": key, "label": "plugin browser"},
        ],
        claim_id=c1["claim_id"],
    )
    assert c2["claim_id"] == c1["claim_id"]
    assert c2["history"][0]["confidence"] == 0.0
    assert c2["history"][0]["level"] == "UNKNOWN"


def test_contradicting_claim_values_are_linked_not_hidden(rig):
    store, caps, obs, key = rig
    kb.save_claim(store, obs["observation_id"], "semantic_name", "plugin.scan.started", 0.0,
                  [{"class": "llm_proposal", "detail": "alternative reading"}])
    second = kb.save_claim(store, obs["observation_id"], "semantic_name", "plugin.catalog.updated", 0.0,
                           [{"class": "llm_proposal", "detail": "primary reading"}])
    assert second["contradictions"], "rival interpretations must be linked"
    linked = kb.contradictions(store)
    assert len(linked) == 2


def test_semantics_propose_stores_zero_and_rejects_bad_shape(rig):
    store, caps, obs, key = rig
    claim = semantics.propose(store, obs["observation_id"], "plugin.catalog.updated", "follows plugin scan", [])
    assert claim["confidence"] == 0.0
    assert claim["level"] == "UNKNOWN", "a proposal with no corroboration explains nothing yet"
    assert claim["verification"]["classes"] == ["llm_proposal"]
    with pytest.raises(PolicyError):
        semantics.propose(store, obs["observation_id"], "Plugin Catalog Updated", "bad name", [])
    with pytest.raises(PolicyError):
        semantics.propose(store, obs["observation_id"], "ok.name", "   ", [])
    with pytest.raises(PolicyError):
        semantics.propose(store, "obs_does_not_exist", "ok.name", "ghost", [])


def test_unknowns_lists_uninterpreted_observations(rig):
    store, caps, obs, key = rig
    un = kb.unknowns(store)
    assert un, "the type 47 observation is uninterpreted and must appear"
    assert any(u["observation_id"] == obs["observation_id"] for u in un)
    semantics.propose(store, obs["observation_id"], "plugin.catalog.updated", "reading", [])
    un_after = kb.unknowns(store)
    assert any(u["observation_id"] == obs["observation_id"] for u in un_after), (
        "a bare proposal (confidence 0.0) does not explain anything; the observation "
        "stays UNKNOWN until corroborating evidence lands — UNKNOWN is honest"
    )


def test_policy_self_description_matches_enforcement():
    pol = kb.policy()
    classes = {c["class"]: c for c in pol["provenance_classes"]}
    assert classes["llm_proposal"]["cap"] == 0.0
    assert classes["captured_traffic"]["verifiable"] is True
    assert pol["corroboration_threshold"] == 0.40
    assert set(c["level"] for c in pol["levels"]) == {lvl for lvl, _, _ in kb.LEVELS}
