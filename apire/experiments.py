"""Experiment proposals — passive protocol fuzzing without fuzzing.

The tool never pokes the target. Instead, it derives from the evidence
graph which *observations the operator could perform* that would
discriminate between current readings or raise a claim's support. Every
proposal is deterministic: it cites the claim or observation that generated
it and states what the result would settle.
"""

from __future__ import annotations

from . import kb, project


def propose(store, subject: str = "", limit: int = 20) -> list[dict]:
    out: list[dict] = []
    claims = store.all_claims()
    captures = store.list_captures()

    # 1. Claims that could be raised: say exactly what would raise them.
    for claim in sorted(claims, key=lambda c: c["confidence"], reverse=True):
        if claim["confidence"] >= 0.80:
            continue
        if subject and claim["subject"] != subject:
            continue
        verified = [v for v in claim["verification"]["verified"] if v["class"] != "captured_traffic"]
        if verified:
            experiment = (
                "capture the same condition again with the other transport (devtools_attach if this "
                "came from http_proxy, or vice versa) to add cross_transport_corroboration"
            )
        else:
            experiment = (
                "run the labeled condition battery twice more (same instrument) and re-correlate; "
                "differential_exclusive needs corroborating labeled captures"
            )
        out.append(
            {
                "kind": "raise_claim",
                "question": f"is {claim['value']!r} ({claim['level']} {claim['confidence']}) really the right reading?",
                "experiment": experiment,
                "would_settle": "would raise or refute the claim with recomputable evidence",
                "evidence_refs": [claim["claim_id"], claim["subject"]],
            }
        )

    # 2. Open contradictions: the discriminating variable.
    for claim in kb.contradictions(store, subject):
        rivals = ", ".join(claim.get("contradictions", []))
        out.append(
            {
                "kind": "resolve_contradiction",
                "question": f"rival readings of {claim['subject']}: {claim['value']!r} vs {rivals}",
                "experiment": (
                    "capture a run whose response body or payload decides between the readings "
                    "(e.g. the endpoint that carries both interpretations), then attach the body-derived "
                    "evidence to the better-supported claim"
                ),
                "would_settle": "one reading gains body/shape evidence; the other stays unverified",
                "evidence_refs": [claim["claim_id"], *claim.get("contradictions", [])],
            }
        )

    # 3. Unlabeled captures: no experiment beats labels.
    for cap in captures:
        if not cap.get("label") and cap["frame_count"] > 0:
            out.append(
                {
                    "kind": "label_capture",
                    "question": f"capture {cap['capture_id']} ({cap['name']}) has no condition label",
                    "experiment": "state what the operator was doing during it (api_re_capture action=label)",
                    "would_settle": "exclusivity analysis becomes meaningful for this capture",
                    "evidence_refs": [cap["capture_id"]],
                }
            )

    # 4. Top unknowns: pair each with the cheapest way to learn about it.
    for row in kb.unknowns(store)[: max(0, limit - len(out))]:
        kind = row["kind"]
        if kind == "http_request" or kind == "http_response":
            experiment = (
                "perform the labeled action you believe touches this endpoint (and one you believe does not), "
                "so differential exclusivity can separate it"
            )
        elif kind == "ws_frame":
            experiment = "trigger the UI area that owns this websocket and capture the open/close cycle"
        else:
            experiment = "capture a run with this component active and one without it, both labeled"
        out.append(
            {
                "kind": "interpret_unknown",
                "question": f"{row['observation_count']} sightings of {row['endpoint'] or row['observation_id']} remain UNKNOWN",
                "experiment": experiment,
                "would_settle": "moves the observation from UNKNOWN to at least HYPOTHESIS with a name proposal",
                "evidence_refs": [row["observation_id"]],
            }
        )

    if subject:
        out = [e for e in out if subject in e["evidence_refs"]]
    return out[:limit]
