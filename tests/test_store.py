"""Capture store: append-only manifests, atomic KB, capture lifecycle."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from apire.errors import PolicyError, StoreError
from apire.store import Store

AUTH = "test fixture authorization: synthetic local traffic"


def _frame(seq=0, key="obs-a"):
    return {
        "kind_hint": "ws_frame",
        "transport": "udp_observe",
        "direction": "server_to_client",
        "capture_seq": seq,
        "payload": {"type": 47, "key": key, "plugins": ["a", "b"], "revision": 3},
    }


def test_capture_requires_authorization_statement(tmp_path):
    store = Store(root=tmp_path)
    with pytest.raises(PolicyError):
        store.start_capture(transport="udp_observe", authorization_statement="")
    with pytest.raises(PolicyError):
        store.start_capture(transport="udp_observe", authorization_statement="   ")


def test_capture_lifecycle_and_manifest_append(tmp_path):
    store = Store(root=tmp_path)
    cap = store.start_capture(transport="udp_observe", name="idle", authorization_statement=AUTH)
    fid = store.append_frame(cap["capture_id"], _frame(0))
    assert fid.startswith("frm_")
    done = store.stop_capture(cap["capture_id"])
    assert done["frame_count"] == 1
    # append after stop is refused: evidence is not silently extended
    with pytest.raises(StoreError):
        store.append_frame(cap["capture_id"], _frame(1))
    assert len(store.list_captures()) == 1


def test_frames_are_immutable_and_ordered(tmp_path):
    store = Store(root=tmp_path)
    cap = store.start_capture(transport="udp_observe", authorization_statement=AUTH)
    for i in range(5):
        store.append_frame(cap["capture_id"], _frame(i))
    frames = store.frames(cap["capture_id"])
    seqs = [f["capture_seq"] for f in frames]
    assert seqs == sorted(seqs) == list(range(5))
    hashes = [f["payload_sha256"] for f in frames]
    assert len(set(hashes[:2])) == 1, "identical frames hash identically"


def test_label_and_note_anchor_to_sequences(tmp_path):
    store = Store(root=tmp_path)
    cap = store.start_capture(transport="udp_observe", authorization_statement=AUTH)
    store.append_frame(cap["capture_id"], _frame(0))
    store.append_frame(cap["capture_id"], _frame(1))
    store.label(cap["capture_id"], label="renamed object", hypothesis="rename emits type 47")
    store.note(cap["capture_id"], seq=1, text="user pressed rename at this frame")
    got = store.get_capture(cap["capture_id"])
    assert got["label"] == "renamed object"
    assert got["hypothesis"] == "rename emits type 47"
    assert [(n["seq"], n["text"]) for n in got["notes"]] == [(1, "user pressed rename at this frame")]


def test_kb_json_is_atomic_and_corruption_raises(tmp_path):
    store = Store(root=tmp_path)
    cap = store.start_capture(transport="udp_observe", authorization_statement=AUTH)
    store.stop_capture(cap["capture_id"])
    kb_path = Path(store.kb_path)
    assert kb_path.exists()
    bak = kb_path.with_suffix(kb_path.suffix + ".bak")
    assert bak.exists(), "one-generation .bak must exist after first write"

    kb_path.write_text("{corrupt", encoding="utf-8")
    with pytest.raises(StoreError):
        Store(root=tmp_path).list_captures()


def test_observations_group_by_canonical_key(tmp_path):
    store = Store(root=tmp_path)
    cap = store.start_capture(transport="udp_observe", authorization_statement=AUTH)
    for i in range(3):
        store.append_frame(cap["capture_id"], _frame(i, key=f"value-{i}"))
    # Same shape, different variable values -> same observable behavior, same key
    store.append_frame(cap["capture_id"], _frame(3, key="value-X"))
    # Different kind -> different key
    store.append_frame(
        cap["capture_id"],
        {
            "kind_hint": "osc_message",
            "transport": "udp_observe",
            "payload": {"address": "/mixer/track/volume", "types": ",f", "args": [0.5]},
        },
    )
    obs = store.build_observations([cap["capture_id"]])
    counts = sorted(o["observation_count"] for o in obs.values())
    kinds = sorted(o["kind"] for o in obs.values())
    assert counts == [1, 4], "same-shape frames group; the OSC address stands alone"
    assert kinds == ["osc_message", "ws_frame"]
    for o in obs.values():
        assert o["capture_refs"] == [cap["capture_id"]]
        assert o["canonical_key"].startswith("ck:")
