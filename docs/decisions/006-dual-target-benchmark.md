# 006. Dual-target benchmark (control + challenge) from day one

- **Status:** accepted
- **Date:** 2026-09-12

## Context

An RE tool that is only ever demonstrated on one opaque target can produce
impressive nonsense; there is no ground truth to contradict it. Conversely, a
tool only ever run on documented APIs has never faced its actual use case.
The project's thesis — evidence-tracked reconstruction — is only demonstrable
with both.

## Decision

Two targets are maintained from M2 onward, with the control target gating
every capability release:

1. **Control** (ground truth): `targets/control/reference_app/` — a local
   application with a committed OpenAPI spec, scripted WS/SSE behavior, and a
   deliberately planted documentation-vs-behavior discrepancy. Scoring is
   computed by deterministic script (`score.py`): endpoint/schema
   precision-recall, event fidelity, contradiction detection, semantic-name
   agreement, plus the binary hard gates (zero secrets leaked, zero egress
   incidents, zero unearned confidence).
2. **Challenge** (darkness): FL Studio 26.1.6 (installer staged, gitignored).
   Hypothesis-first capture sessions, human-performed action batteries,
   audited semantic map. Success is a map that survives an independent
   evidence audit, not a score.

Rule: **no capability ships that has not first measurably worked on the
control target.** The challenge target never gates releases; it gates claims.

## Alternatives considered

- *Control only:* rejected — tests the instrument, never the mission.
- *Challenge only:* rejected — unfalsifiable; exactly the "cool RE demo" the
  user refused to build.
- *Third-party documented API as primary control:* kept as the M5+ ecological
  tier, but not primary — external apps change under us; the reference app
  makes the benchmark deterministic.

## Consequences

- `targets/control/reference_app/` is a product in the repo: it must itself be
  tested (it serves the fixtures the benchmark scores against).
- FL Studio campaign results are recorded as evidence exports, not prose
  claims, so re-audits are mechanical.

## Review trigger

A milestone where control metrics regress, or the challenge campaign
repeatedly produces claims that cannot reach INFERRED (instruments may be
missing a transport).
