"""The evidence KB: closed provenance vocabulary, caps, deterministic
verifiers. Remcp's policy contract, re-derived for observed traffic:

- confidence must not exceed the highest cap among the claim's classes;
- confidence above 0.40 requires >= 2 distinct classes;
- verifiable classes are RECOMPUTED against the store — a failed check
  rejects the write with PolicyError. A claim that cannot re-derive from
  captured evidence does not exist.

`llm_proposal` carries cap 0.00: a model's interpretation can never, by
itself or twice over, raise a claim past HYPOTHESIS. Only capture-derived
classes raise claims. That is the enforcement of "the model proposes; the
evidence decides".
"""

from __future__ import annotations

from datetime import datetime, timezone

from . import correlate
from .errors import PolicyError
from .normalize import shape_signature

LEVELS = [
    ("CONFIRMED", 0.95, 1.00),
    ("OBSERVED", 0.80, 0.95),
    ("STRONGLY_INFERRED", 0.60, 0.80),
    ("INFERRED", 0.40, 0.60),
    ("HYPOTHESIS", 0.10, 0.40),
    ("UNKNOWN", 0.00, 0.10),
]

CORROBORATION_THRESHOLD = 0.40
MIN_CLASSES_ABOVE_THRESHOLD = 2

# class -> (cap, verifiable, requires_artifact)
CLASSES: dict[str, tuple[float, bool, bool]] = {
    "captured_traffic": (0.95, True, True),
    "differential_exclusive": (0.80, True, True),
    "temporal_correlation": (0.60, True, True),
    "cross_transport_corroboration": (0.70, True, True),
    "schema_induction": (0.60, True, True),
    "field_discrimination": (0.70, True, True),
    "js_static_analysis": (0.40, True, True),
    "string_reference": (0.30, True, True),
    "authoritative_spec": (1.00, False, True),
    "human_observation_label": (0.95, False, True),
    "community_source": (0.50, False, True),
    "llm_proposal": (0.00, False, False),
}

CLAIM_KINDS = {
    "semantic_name",
    "direction",
    "correlation",
    "schema",
    "side_effect",
    "authentication",
    "ordering",
    "existence",
    "relationship",
}


def policy() -> dict:
    return {
        "levels": [{"level": lvl, "min": lo, "max": hi} for lvl, lo, hi in LEVELS],
        "corroboration_threshold": CORROBORATION_THRESHOLD,
        "min_classes_above_threshold": MIN_CLASSES_ABOVE_THRESHOLD,
        "provenance_classes": [
            {"class": name, "cap": cap, "verifiable": ver, "requires_artifact": art}
            for name, (cap, ver, art) in CLASSES.items()
        ],
        "claim_kinds": sorted(CLAIM_KINDS),
        "law": "a claim that cannot re-derive from captured evidence does not exist",
    }


def level_for(confidence: float) -> str:
    for level, lo, hi in LEVELS:
        if lo <= confidence <= hi:
            return level
    return "UNKNOWN"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _verify_class(store, subject: str, prov: dict) -> tuple[bool, str]:
    cls = prov["class"]
    artifact = prov.get("artifact") or ""
    if cls == "captured_traffic":
        if subject.startswith("obs_"):
            obs = store.find_observation(subject)
            if obs is None:
                return False, f"observation {subject} not found in store"
            return True, f"observation exists: {obs['observation_count']} sightings across {len(obs['capture_refs'])} captures"
        if subject.startswith("frm_"):
            for frame in store.iter_frames():
                if frame["frame_id"] == subject:
                    return True, "frame exists, payload hash matches"
            return False, f"frame {subject} not found in store"
        return False, f"captured_traffic subject must be an obs_ or frm_ id, got '{subject[:40]}'"
    if cls == "differential_exclusive":
        capture_ids = prov.get("capture_ids") or []
        key = prov.get("canonical_key") or (artifact if artifact.startswith("ck:") else "")
        label = prov.get("label") or ""
        if not (capture_ids and key and label):
            return False, "differential_exclusive needs capture_ids, canonical_key, label"
        return correlate.recompute_exclusive(store, capture_ids, key, label)
    if cls == "temporal_correlation":
        capture_id = prov.get("capture_id") or ""
        after_seq = prov.get("after_seq")
        if not (capture_id and after_seq is not None):
            return False, "temporal_correlation needs capture_id and after_seq"
        obs = store.find_observation(subject)
        if obs is None:
            return False, f"subject {subject} not found"
        after = [s for s in obs["sightings"] if s["capture_id"] == capture_id and s["capture_seq"] > after_seq]
        if after:
            return True, f"{len(after)} sighting(s) follow seq {after_seq} in {capture_id}"
        return False, f"no sighting of {subject} follows seq {after_seq} in {capture_id}"
    if cls == "schema_induction":
        obs = store.find_observation(subject if subject.startswith("obs_") else "")
        if obs is None:
            return False, f"subject {subject} not found as an observation"
        return True, f"induced shape recomputed live: sig {shape_signature(obs['shape'])[:40]}"
    # Non-recomputable classes this far: recorded as asserted, never verified.
    return True, f"class '{cls}' is asserted, not recomputed (no verifier yet)"


def save_claim(
    store,
    subject: str,
    kind: str,
    value,
    confidence: float,
    provenance: list[dict],
    note: str = "",
    claim_id: str | None = None,
) -> dict:
    if kind not in CLAIM_KINDS:
        raise PolicyError(f"unknown claim kind '{kind}'", vocabulary=sorted(CLAIM_KINDS))
    if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
        raise PolicyError(f"confidence must be a number in [0,1], got {confidence!r}")
    if not provenance:
        raise PolicyError("a claim without provenance does not exist")
    for prov in provenance:
        if prov.get("class") not in CLASSES:
            raise PolicyError(f"unknown provenance class '{prov.get('class')}'", vocabulary=sorted(CLASSES))
        if CLASSES[prov["class"]][2] and not (prov.get("artifact") or _artifact_from_context(prov)):
            raise PolicyError(
                f"class '{prov['class']}' requires an artifact reference (capture/frame/bundle/spec id)"
            )

    cap = max(CLASSES[p["class"]][0] for p in provenance)
    if confidence > cap:
        raise PolicyError(
            f"confidence {confidence} exceeds the highest class cap {cap}",
            cap=cap,
            classes=sorted({p["class"] for p in provenance}),
        )
    distinct = {p["class"] for p in provenance}
    if confidence > CORROBORATION_THRESHOLD and len(distinct) < MIN_CLASSES_ABOVE_THRESHOLD:
        raise PolicyError(
            f"confidence above {CORROBORATION_THRESHOLD} requires at least "
            f"{MIN_CLASSES_ABOVE_THRESHOLD} distinct provenance classes, got {sorted(distinct)}",
            classes=sorted(distinct),
        )

    verified, asserted = [], []
    for prov in provenance:
        ok, detail = _verify_class(store, subject, prov)
        if CLASSES[prov["class"]][1] and not ok:
            raise PolicyError(
                f"verifiable class '{prov['class']}' failed recomputation: {detail}",
                provenance_class=prov["class"],
                detail=detail,
            )
        record = {"class": prov["class"], "detail": detail}
        (verified if CLASSES[prov["class"]][1] else asserted).append(record)

    claims = store.all_claims()
    existing = next((c for c in claims if c["claim_id"] == claim_id), None)
    claim = existing or {
        "claim_id": claim_id or ("clm_" + _uid16()),
        "subject": subject,
        "kind": kind,
        "created_utc": _now(),
        "history": [],
    }
    if existing and (existing["confidence"] != confidence or existing["value"] != value):
        claim["history"].append(
            {
                "value": existing["value"],
                "confidence": existing["confidence"],
                "level": existing["level"],
                "superseded_utc": _now(),
            }
        )
    claim.update(
        {
            "kind": kind,
            "value": value,
            "confidence": float(confidence),
            "level": level_for(float(confidence)),
            "provenance": [
                {
                    "class": p["class"],
                    "artifact": p.get("artifact") or _artifact_from_context(p) or "",
                    "detail": p.get("detail", ""),
                    "capture_ids": p.get("capture_ids", []),
                    "capture_id": p.get("capture_id", ""),
                    "after_seq": p.get("after_seq"),
                    "canonical_key": p.get("canonical_key", ""),
                    "label": p.get("label", ""),
                }
                for p in provenance
            ],
            "verification": {
                "cap_applied": cap,
                "classes": sorted(distinct),
                "verified": verified,
                "asserted": asserted,
            },
            "note": note,
            "updated_utc": _now(),
        }
    )
    store.upsert_claim(claim)
    _link_contradictions(store, claim)
    return claim


def _artifact_from_context(prov: dict) -> str:
    if prov.get("capture_ids"):
        return "captures:" + ",".join(prov["capture_ids"])
    if prov.get("capture_id"):
        return "capture:" + prov["capture_id"]
    return ""


def _uid16() -> str:
    import secrets

    return secrets.token_hex(8)


def _link_contradictions(store, claim: dict) -> None:
    """Claims of the same kind on the same subject with different values argue
    against each other. Contradictions are kept, not resolved by force."""
    claims = store.all_claims()
    rivals = [
        c
        for c in claims
        if c["claim_id"] != claim["claim_id"]
        and c["subject"] == claim["subject"]
        and c["kind"] == claim["kind"]
        and c["value"] != claim["value"]
    ]
    ids = sorted(c["claim_id"] for c in rivals)
    claim["contradictions"] = ids
    for rival in rivals:
        ids_r = set(rival.get("contradictions") or [])
        ids_r.add(claim["claim_id"])
        rival["contradictions"] = sorted(ids_r)
        store.upsert_claim(rival)


def get_claim(store, claim_id: str) -> dict:
    for c in store.all_claims():
        if c["claim_id"] == claim_id:
            return c
    raise PolicyError(f"unknown claim '{claim_id}'", hint="use api_re_evidence action=query to list claims")


def query(store, subject: str = "", min_level: str = "", provenance_class: str = "") -> list[dict]:
    order = {lvl: i for i, (lvl, _, _) in enumerate(LEVELS)}
    out = []
    for c in store.all_claims():
        if subject and c["subject"] != subject:
            continue
        if min_level and order.get(c["level"], 99) > order.get(min_level, 0):
            continue
        if provenance_class and provenance_class not in c["verification"]["classes"]:
            continue
        out.append(c)
    out.sort(key=lambda c: -c["confidence"])
    return out


def contradictions(store, subject: str = "") -> list[dict]:
    out = [c for c in store.all_claims() if c.get("contradictions") and (not subject or c["subject"] == subject)]
    out.sort(key=lambda c: c["subject"])
    return out


def unknowns(store) -> list[dict]:
    """Observed-but-uninterpreted: observations with no claim at confidence
    >= HYPOTHESIS floor. A bare proposal (confidence 0.0) is not an
    explanation; the observation stays unknown until evidence lands.
    Ranked by salience (count), honestly."""
    claims = store.all_claims()
    explained = {c["subject"] for c in claims if c["confidence"] >= 0.10}
    out = []
    for obs in store.build_observations(_all_capture_ids(store)).values():
        if obs["observation_id"] in explained:
            continue
        if obs["kind"] in ("process_meta",):
            continue
        out.append(
            {
                "observation_id": obs["observation_id"],
                "kind": obs["kind"],
                "endpoint": obs["endpoint_template"],
                "observation_count": obs["observation_count"],
                "shape": obs["shape"],
            }
        )
    out.sort(key=lambda o: -o["observation_count"])
    return out[:100]


def _all_capture_ids(store) -> list[str]:
    return [c["capture_id"] for c in store.list_captures()]
