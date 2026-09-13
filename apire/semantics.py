"""The LLM intake valve.

The only write path for interpretations. A proposal is stored verbatim at
confidence 0.0 with `llm_proposal` provenance (cap 0.00 — the policy makes
"the model declared it" worth exactly nothing on its own). Proposals become
knowledge only when capture-derived evidence is added on top, through the
same policy gate as everything else.
"""

from __future__ import annotations

import re

from . import kb
from .errors import PolicyError

_NAME_RE = re.compile(r"^[a-z][a-z0-9_.]*$")


def propose(store, subject: str, proposed_name: str, rationale: str, evidence_refs: list[str] | None = None) -> dict:
    if not _NAME_RE.match(proposed_name or ""):
        raise PolicyError(
            f"proposed_name '{proposed_name}' must be dotted-lowercase (e.g. plugin.catalog.updated)",
        )
    if not (rationale or "").strip():
        raise PolicyError("rationale is required: the proposal is stored verbatim, so argue your case")
    if subject.startswith("obs_") and store.find_observation(subject) is None:
        raise PolicyError(f"subject '{subject}' is not an observation in the store", hint="propose against real observations only")
    return kb.save_claim(
        store,
        subject=subject,
        kind="semantic_name",
        value=proposed_name,
        confidence=0.0,
        provenance=[{"class": "llm_proposal", "detail": rationale}],
        note="; ".join(evidence_refs or []),
    )


def raise_confidence(store, claim_id: str, added_provenance: list[dict], confidence: float) -> dict:
    """Attach capture-derived evidence to a proposal. Same gate as any claim:
    the new classes must verify by recomputation."""
    claim = kb.get_claim(store, claim_id)
    merged = list(claim["provenance"]) + list(added_provenance)
    return kb.save_claim(
        store,
        subject=claim["subject"],
        kind=claim["kind"],
        value=claim["value"],
        confidence=confidence,
        provenance=merged,
        note=claim.get("note", ""),
        claim_id=claim_id,
    )


def review(store, claim_id: str) -> dict:
    claim = kb.get_claim(store, claim_id)
    corroboration = [
        v for v in claim["verification"]["verified"] if v["class"] not in ("captured_traffic",)
    ]
    # A claim whose subject no longer resolves (normalizer/version change
    # re-keyed the observations) is stranded: still visible, no longer
    # re-verifiable. Say so instead of pretending.
    subject = claim["subject"]
    resolves = None
    if subject.startswith("obs_"):
        resolves = store.find_observation(subject) is not None
    standing = {
        "level": claim["level"],
        "confidence": claim["confidence"],
        "cap": claim["verification"]["cap_applied"],
        "what_would_raise_it": (
            "corroborating labeled captures under a different condition label "
            "(differential_exclusive), or a second independent transport "
            "(cross_transport_corroboration)"
        ),
        "what_would_lower_it": "a capture showing the subject under a contradicting condition",
        "corroborating_verifications": len(corroboration),
        "contradictions": claim.get("contradictions", []),
        "subject_resolves": resolves,
    }
    if resolves is False:
        standing["subject_note"] = (
            "subject observation no longer resolves against the current store "
            "(a normalizer or instrument change re-keyed observations). The claim is "
            "stranded: re-anchor it by proposing against the current observation."
        )
    return {"claim": claim, "standing": standing}


def link(store, claim_id: str, related_claim_ids: list[str]) -> dict:
    kb.get_claim(store, claim_id)
    for rid in related_claim_ids:
        kb.get_claim(store, rid)
    relation = kb.save_claim(
        store,
        subject=claim_id,
        kind="relationship",
        value={"related": sorted(related_claim_ids)},
        confidence=0.0,
        provenance=[{"class": "llm_proposal", "detail": f"proposed relation to {sorted(related_claim_ids)}"}],
    )
    return relation
