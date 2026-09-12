# Control target — documented reference application

The instrument is only trusted after it measures something known.

## reference_app/ (built in M2)

A small local application with a *committed* API specification it does and
does not follow:

- REST endpoints covering the realistic cases: path/query params, pagination,
  polymorphic payloads, nested resources, error semantics.
- Authentication via `Authorization: Bearer <fixture>` headers — chosen so
  the redaction gate is exercised on every request, with **fixture** tokens
  only (any real-looking token in these fixtures is a defect).
- A WebSocket event stream + one SSE endpoint (exercised from M6).
- One endpoint **documented incorrectly on purpose**: the spec says field
  `created_at: string(date)` where the app emits `created_ts: integer(epoch)`.
  The benchmark's highest-value assertion is that apire reports this as an
  `authoritative_spec` vs `captured_traffic` contradiction instead of
  silently picking a side.

## Scoring

`score.py` (M2) computes the metrics table in
[docs/evaluation.md](../docs/evaluation.md) by comparing the evidence-graph
projection against `openapi.json` — a deterministic script, never an LLM's
opinion. Hard gates (zero leaked secrets, zero egress incidents, zero
unearned confidence) are binary and release-blocking.

## Ecological tier (M5+)

A real open-source service with a published spec (candidates in the
workspace: `open5e-api`, Gitea). Same scoring, no control over reality.
