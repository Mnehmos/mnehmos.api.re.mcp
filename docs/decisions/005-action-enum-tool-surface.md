# 005. Action-enum tool surface (seven tools)

- **Status:** accepted
- **Date:** 2026-09-12

## Context

Two forces set the tool count:

1. The workspace action-enum doctrine (`F:/Github/MCP_CONSOLIDATION_PLAN.md`):
   GLM rejects registration above ~89–94 tools; one-tool-per-operation (remcp's
   28) is the documented outlier being migrated away from. New servers start
   consolidated: ≤ 8 actions per tool, ≤ 6 tools per server as the target.
2. The governing rule benefits from a small surface: every action that does
   not exist cannot be misused.

The doctrine says ≤ 6 tools *target*. This design lands on 7.

## Decision

Seven tools: `api_re_capture`, `api_re_observations`, `api_re_protocol`,
`api_re_architecture`, `api_re_evidence`, `api_re_semantics`,
`api_re_export`. One over the target, accepted deliberately:

- Merging `api_re_semantics` (the write valve) into any read tool violates
  least-authority — a caller granted read access must not hold the
  interpretation valve.
- `api_re_policy` folds into `api_re_evidence` as an action (`policy`) rather
  than standing alone as remcp's `re_kb_policy` does.
- 7 tools × ~4–6 actions ≈ 33 actions, well within every budget.

Dispatch is strict per-action unions behind the advertised enum; optional
parameters take plain defaults, never `Optional[...]` (FastMCP emits
`anyOf: [T, null]` for Optional, which strict providers reject — the
consolidation plan's finding).

## Alternatives considered

- *remcp-style one tool per operation (~30 tools):* rejected — it is the exact
  pattern the workspace is migrating away from, and a wide surface weakens the
  no-transmission guarantee's auditability.
- *Six tools by merging semantics into evidence:* rejected above.
- *Dotted tool names (`api_re.capture`):* not expressible — MCP tool names
  allow `[a-zA-Z0-9_-]` only; underscores it is.

## Consequences

- Per-action docs live in one schema union; the enum is the advertisement,
  dispatch is the law.
- `UnsupportedError` on actions whose milestone has not landed — refusal over
  guessing, and the surface shape is stable from M2 even when capability is
  not.

## Review trigger

If any tool exceeds 8 actions, or if two tools' action sets overlap enough
that callers cannot tell which to call.
