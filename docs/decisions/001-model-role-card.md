# 001. Model role card

- **Status:** accepted
- **Date:** 2026-09-12

## Role split

| Concern | Owner |
| ------- | ----- |
| Driving the tool loop (which captures to take, what to inspect next) | LLM (runtime) |
| Proposing semantic names, relations, interpretations | LLM (runtime, via `api_re_semantics`) |
| Designing discriminating experiments | LLM proposes, human performs |
| Capture, redaction, storage | deterministic engine |
| Normalization, correlation, schema induction | deterministic engine |
| Evidence verdicts (confidence, level, admission) | deterministic policy + verifiers |
| Export projection | deterministic engine |
| Truth (what was observed) | the capture store — never the model |

## Per-tool architecture cards (filled as each tool lands)

| Tool | Model may propose | Source of truth | Commit boundary | Rejection behavior |
| ---- | ----------------- | --------------- | --------------- | ------------------ |
| `api_re_capture` | transport choice, filters, labels | capture store | frame persisted = real | `TransportError` / `PolicyError` (no authorization statement) |
| `api_re_observations` | query shapes | capture store | read-only | `StoreError` on corruption, in-band |
| `api_re_protocol` | filters | evidence graph | read-only | in-band empty + unknowns pointer |
| `api_re_architecture` | filters | evidence graph | read-only | in-band |
| `api_re_evidence` | filters | evidence graph | read-only | in-band |
| `api_re_semantics` | names, relations, rationales | evidence graph | proposal stored @ cap 0.0; verdict separate | shape violations rejected; wrongness is not rejection, it is low confidence |
| `api_re_export` | format, min_level, path | evidence graph | file written | `ExportError` with unmet-floor summary |

## Consequences

- The model can be creative exactly where creativity pays (naming, relating,
  experiment design) and is structurally incapable of manufacturing truth.
- Review trigger: if verifiers ever need to trust a model-supplied fact
  (not proposal), this card is violated and the design has drifted.
