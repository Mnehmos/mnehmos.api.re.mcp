# Evidence model

First principle: **plausibility is a proposal's ticket to be considered; it is
never a ticket to commit.** Confidence is never evidence. Every stored claim
carries provenance that a verifier recomputed from the capture store — or it
does not reach the store.

## Evidence levels

Closed vocabulary, six levels, each with a numeric confidence band. Level is
derived from confidence; confidence is bounded by provenance class caps.

| Level | Band | Granted when |
| ----- | ---- | ------------ |
| `CONFIRMED` | 0.95 – 1.00 | claim matches an authoritative source (e.g., the target's published spec) or is human-verified against the artifact |
| `OBSERVED` | 0.80 – 0.95 | claim is directly present in captured traffic and re-derivable from a capture artifact |
| `STRONGLY_INFERRED` | 0.60 – 0.80 | corroborated by ≥ 2 independent labeled captures or ≥ 2 distinct verifiable provenance classes |
| `INFERRED` | 0.40 – 0.60 | pattern from a single capture: schema induction, shape families, ordering seen once |
| `HYPOTHESIS` | 0.10 – 0.40 | a model proposal with weak corroborating evidence |
| `UNKNOWN` | 0.00 – 0.10 | observed but uninterpretable; explicitly stored, not discarded |

Machine values use the underscore forms above (`STRONGLY_INFERRED`); prose may
write "strongly inferred".

A claim whose confidence drops below its band on revision is *downgraded with
history* (previous confidence/provenance append to `history[]`), never silently
rewritten — the remcp revision contract.

## Provenance classes (closed vocabulary)

Mirrors remcp `kb.py`: each class has a confidence **cap**, a
**verifiable** flag (a deterministic verifier recomputes the claim against
artifacts; failure rejects the write with `PolicyError`), and a
**requires_artifact** flag.

| Class | Cap | Verifiable | Requires artifact | Verifier recomputes from |
| ----- | --- | ---------- | ----------------- | ------------------------ |
| `captured_traffic` | 0.95 | yes | yes | capture + frame IDs exist; frame hash matches; payload contains the claimed element |
| `differential_exclusive` | 0.80 | yes | yes | recompute exclusivity counts across the cited labeled captures |
| `temporal_correlation` | 0.60 | yes | yes | recompute ordering relation in ≥ the cited captures; ≥ 2 captures required above 0.60 |
| `cross_transport_corroboration` | 0.70 | yes | yes | same fact re-derived from ≥ 2 transports (e.g., HTTP response + WS event) |
| `schema_induction` | 0.60 | yes | yes | cited observations still conform to the induced schema |
| `field_discrimination` | 0.70 | yes | yes | the designed-experiment variance analysis reproduces (length-correlated field etc.) |
| `js_static_analysis` | 0.40 | yes | yes | symbol/string/AST fact present in the cited bundle artifact |
| `string_reference` | 0.30 | yes | yes | literal present in cited artifact (log line, bundle, error text) |
| `authoritative_spec` | 1.00 | no | yes | artifact pinned by content hash (published OpenAPI/docs); checked for existence + hash, not re-derived |
| `human_observation_label` | 0.95 | no | yes | the human's condition label on a capture ("user renamed object") — trusted as experimental ground truth *for the label only* |
| `community_source` | 0.50 | no | yes | cited URL/reference; recorded unverified |
| `llm_proposal` | **0.00** | no | no | nothing — a proposal carries zero confidence, always |

**Corroboration rule** (remcp contract): confidence above 0.40 requires
≥ 2 distinct provenance classes above the 0.40 threshold. `llm_proposal`
participates in the count with cap 0.0, which means: **a model's interpretation
can never by itself, or twice-over, raise a claim past INFERRED.** Only capture-
derived classes can. This is the enforcement of "the model shouldn't be trusted
to declare that 47 == plugin.catalog.updated; it proposes the interpretation;
the deterministic evidence system tracks exactly why."

## Worked example: `type: 47`

```text
Subject  : ws:message[type=47] @ transport=websocket, channel=app-main
Claim    : semantic_name = "plugin.catalog.updated"
Direction: server -> client

api_re_semantics propose (the LLM's move)
  -> stored: provenance [llm_proposal], confidence 0.00, level UNKNOWN
     (a proposal with no corroboration is an interpretation attempt, not an
     explanation: it does not remove the observation from `unknowns`)
  -> rationale stored verbatim; proposal cannot be rejected for being wrong,
     only for violating shape/policy. Wrongness is settled by evidence, not
     by a gatekeeper's taste.

Evidence accumulating (deterministic, recomputable):
  differential_exclusive   "appears only in plugin-browser captures" 18/18, 7/7, 6/6
  temporal_correlation     "follows plugin-scan completion marker" in 14 captures
  schema_induction         payload {plugins: Plugin[], revision: integer}
  counter_evidence         2 captures where type 47 followed plugin *removal*

api_re_evidence explain:
  level STRONGLY INFERRED  confidence 0.78
  verified: [{class: differential_exclusive, detail: "recomputed 31/31 sightings inside
              labeled condition sets, 0 outside"}]
  contradictions: [{claim: "follows plugin-scan", detail: "2 removal-following sightings"}]
  next experiment: "install a plugin during capture; does type 47 revision increment?"

The path to 0.91+ (CONFIRMED) runs through the *human* verifying against the
vendor's documentation, or the vendor's own spec artifact — nothing else.
```

## Contradictions, unknowns, and the honesty surface

- **Contradictions** are first-class: evidence that argues against a stored
  claim is linked, not discarded. A claim with unresolved contradictions is
  marked degraded in any envelope that includes it.
- **Unknowns** are stored observations that resist interpretation
  (`UNKNOWN` level) — the tool's memory of what it does not understand.
  `api_re_evidence unknowns` lists them ranked by salience (frequency ×
  unexplainedness).
- **Experiments** (`api_re_evidence experiments`) proposes discriminating
  observations the *human* could perform next ("rename the same object twice
  with names of different lengths"), each targeting a specific open question
  in the graph. The tool never performs them; proposing them is its most
  active behavior. This is passive protocol fuzzing without fuzzing: hypothesis
  testing by designed observation, with the human as the actuator.

## What the policy rejects (hard)

- Confidence exceeding the max cap of the claim's provenance classes.
- Confidence > 0.40 without ≥ 2 distinct classes above threshold.
- A `verifiable` class whose verifier fails recomputation — the write is
  rejected with `PolicyError` carrying machine-readable context
  (`cap`, `classes`, `vocabulary`, detail), exactly like remcp.
- A claim whose required artifact (capture ID / frame ID / bundle hash) is
  missing from the store.
- Every stored claim keeps its verification record
  (`{cap_applied, classes, verified[], asserted[]}`) distinguishing what the
  machine checked from what was trusted. Absence of a hit is not evidence of
  absence; the record says which one you are looking at.
