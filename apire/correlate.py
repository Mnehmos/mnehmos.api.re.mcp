"""Differential correlation: labeled capture spans compared against each other.

First principle: a claim about a difference must be recomputable from the
store, so every function here is a pure read over frames and returns the
numbers it based its judgment on (the 18/18, 7/7, 6/6 of the worked example).
"""

from __future__ import annotations

import statistics

from .errors import StoreError


def _condition(store, capture_id: str) -> dict:
    cap = store.get_capture(capture_id)
    return {
        "capture_id": capture_id,
        "label": cap.get("label") or f"unlabeled:{cap['name']}",
        "instrument": cap.get("instrument", ""),
        "frame_count": cap["frame_count"],
        "notes": cap.get("notes", []),
    }


def instrument_mismatch(store, capture_ids: list[str]) -> dict:
    """Captures taken with different instrument versions/granularities are a
    confound: a signal 'exclusive' to one condition may be exclusive to the
    instrument instead. Detect it loudly rather than reporting it as
    evidence."""
    instruments = {}
    for cid in capture_ids:
        cap = store.get_capture(cid)
        instruments[cid] = cap.get("instrument", "unknown")
    distinct = sorted(set(instruments.values()))
    return {"mismatch": len(distinct) > 1, "instruments": instruments, "distinct": distinct}


def _sightings_by_capture(obs: dict) -> dict[str, list[int]]:
    by: dict[str, list[int]] = {}
    for s in obs.get("sightings", []):
        by.setdefault(s["capture_id"], []).append(s["capture_seq"])
    for cap_id in by:
        by[cap_id].sort()
    return by


def is_periodic(obs: dict) -> dict | None:
    """An observation arriving at a regular interval in some capture is
    heartbeat noise: it is excluded from exclusivity claims and reported as
    its own kind of evidence instead of poisoning the diff."""
    for cap_id, seqs in _sightings_by_capture(obs).items():
        if len(seqs) < 4:
            continue
        deltas = [b - a for a, b in zip(seqs, seqs[1:])]
        if not deltas:
            continue
        mean = statistics.mean(deltas)
        if mean > 0 and statistics.pstdev(deltas) / mean < 0.25:
            return {"capture_id": cap_id, "interval_frames": round(mean, 2)}
    return None


def compare(store, capture_ids: list[str]) -> dict:
    """Per canonical key: which captures saw it, how often, exclusive to what."""
    if len(capture_ids) < 2:
        raise StoreError("compare needs at least 2 capture ids")
    obs_index = store.build_observations(capture_ids)
    rows = []
    for key, obs in sorted(obs_index.items()):
        counts = {cid: 0 for cid in capture_ids}
        for s in obs["sightings"]:
            if s["capture_id"] in counts:
                counts[s["capture_id"]] += 1
        present = [cid for cid, n in counts.items() if n > 0]
        exclusive_to = present if len(present) == 1 else None
        rows.append(
            {
                "canonical_key": key,
                "observation_id": obs["observation_id"],
                "endpoint": obs["endpoint_template"],
                "kind": obs["kind"],
                "counts": counts,
                "total": obs["observation_count"],
                "exclusive_to": exclusive_to,
            }
        )
    rows.sort(key=lambda r: -r["total"])
    return {
        "captures": [_condition(store, cid) for cid in capture_ids],
        "rows": rows,
        "instrument_check": instrument_mismatch(store, capture_ids),
    }


def correlate(store, capture_ids: list[str]) -> dict:
    """The differential view: exclusivity by condition label, periodic noise
    separated out, and the candidate signals worth a semantic proposal."""
    diff = compare(store, capture_ids)
    conditions = {c["capture_id"]: c["label"] for c in diff["captures"]}

    exclusivity = []
    periodic = []
    candidates = []
    for row in diff["rows"]:
        obs = store.build_observations(list(row["counts"]))[row["canonical_key"]]
        per_label: dict[str, int] = {}
        for cid, n in row["counts"].items():
            per_label[conditions[cid]] = per_label.get(conditions[cid], 0) + n
        labels_present = sorted({conditions[cid] for cid, n in row["counts"].items() if n > 0})
        periodicity = is_periodic(obs)
        entry = {
            "canonical_key": row["canonical_key"],
            "observation_id": row["observation_id"],
            "endpoint": row["endpoint"],
            "kind": row["kind"],
            "per_label": per_label,
            "labels_present": labels_present,
            "periodic": periodicity,
        }
        if periodicity:
            periodic.append(entry)
            continue
        exclusivity.append(entry)
        # Candidate signal: seen under exactly one labeled condition, never
        # under any other labeled condition, seen more than once.
        labels_with_captures = {conditions[cid] for cid in capture_ids if _condition(store, cid)["frame_count"] > 0}
        if len(labels_present) == 1 and len(labels_with_captures) > 1 and row["total"] >= 2:
            entry = dict(entry)
            entry["exclusive_label"] = labels_present[0]
            entry["evidence_counts"] = {
                lbl: f"{per_label.get(lbl, 0)}/{per_label.get(lbl, 0) if lbl in per_label else sum(n for cid, n in row['counts'].items() if conditions[cid] == lbl)}"
                for lbl in sorted(labels_with_captures)
            }
            candidates.append(entry)
    return {
        "conditions": diff["captures"],
        "instrument_check": diff["instrument_check"],
        "exclusivity": exclusivity[:200],
        "exclusivity_count": len(exclusivity),
        "periodic_noise": periodic[:100],
        "periodic_count": len(periodic),
        "candidates": candidates[:100],
        "candidate_count": len(candidates),
        "warning_unlabeled": any(c["label"].startswith("unlabeled:") for c in diff["captures"]),
    }


def recompute_exclusive(store, capture_ids: list[str], canonical_key: str, label: str) -> tuple[bool, str]:
    """Verifier for the differential_exclusive provenance class: does the key
    still appear only under captures carrying `label`, never under any other
    labeled capture in the cited set?"""
    try:
        obs = store.build_observations(capture_ids)[canonical_key]
    except KeyError:
        return False, f"canonical key {canonical_key} not present in cited captures"
    per: dict[str, int] = {}
    for cid in capture_ids:
        cap = store.get_capture(cid)
        cid_label = cap.get("label") or f"unlabeled:{cap['name']}"
        n = sum(1 for s in obs["sightings"] if s["capture_id"] == cid)
        if n:
            per[cid_label] = per.get(cid_label, 0) + n
    others = {lbl: n for lbl, n in per.items() if lbl != label}
    if not per:
        return False, "no sightings in cited captures"
    if others:
        return False, f"also seen under {others}"
    if is_periodic(obs):
        return False, f"periodic in cited captures ({is_periodic(obs)})"
    seen = per.get(label, 0)
    return True, f"recomputed {seen}/{seen} sightings under '{label}', 0 under other labels in cited set"
