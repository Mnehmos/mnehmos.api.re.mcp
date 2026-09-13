# Session handoff — 2026-09-12 (M6: bodies, SSE, FL audit)

## Session metadata

- Branch: main
- Last commit: feat: M6 — response bodies, SSE relay, FL claim audit
- Test status: `74 passed` (pytest, incl. benchmark) and `17 passed, 0
  failed` (tests/wire_test.py)

## Current state

M0–M6 complete; only OSC remains and it needs a human (in-app enable in
FL's settings). This session:

- `devtools_attach` v2: response bodies (opt-in `bodies=true`, 2 MB fetch
  cap, 16 KB sample, in-flight command tracking, stop-flush accounting) and
  WS lifecycle events. Two bugs found and fixed by dogfooding (see
  CHANGELOG 0.4.0).
- `http_proxy`: SSE streams relay incrementally and yield `sse_event`
  frames; two more bugs caught by the new test (buffer bypass, CRLF).
- Normalizer: exact-status response keys; `@body` array representation;
  exporters emit real array schemas.
- FL: capture `cap_5350bc449977` (bodies), the Unleash-vs-config rivalry
  **settled by evidence** (toggles JSON), Sentry identified, three claims at
  STRONGLY_INFERRED, audit published (12 claims / 64 unknowns / 1 stranded
  claim flagged). Details: targets/fl-studio/README.md.

## Decision log

- Response keys moved from status-class to exact status mid-session: it
  immediately revealed `HTTP 200 /api/frontend` (toggles) as distinct from
  its 204/OPTIONS siblings. Cost: it stranded the earlier sentry claim
  reference (policy refused my stale id — visible in the session log) and
  one INFERRED claim now shows `subject_resolves: false`. Both are the
  documented re-anchor case, not corruption.
- `@body` array representation chosen over fabricating field names: an
  array body has no fields, and lying about that would poison schema
  exports.
- Host-in-keys deferred (ADR-009) with evidence and plan; the missing piece
  (normalizer version in KB header) is recorded there as part of the plan.
- SSE handled in the proxy rather than deferred: without it the proxy
  breaks the observed app on event-stream responses (correctness, not
  feature).

## Deferred / human-gated

- **OSC: falsified, no longer human-gated.** FL 26.1.6 has no OSC support
  (all ten Settings tabs checked, engine string table silent, 25-minute
  passive listen recorded 0 frames). Evidence in
  targets/fl-studio/evidence/h1-osc-falsified/.
- ADR-009 keying v2 + re-anchor pass: deliberate isolated change.
- 2 MB body-fetch cap: raise when a schema question needs the big Next.js
  JSONs.
- Ecological benchmark tier (open5e-api/Gitea).

## Known blockers

None technical. FL Studio is running with the debug port enabled.

## Next step (exactly one)

Implement ADR-009 (host in HTTP canonical keys) with the KB normalizer
version bump, then re-anchor every claim whose `explain` reports
`subject_resolves: false` — the stranded set is currently one claim.

## CLAUDE.md changed?

- [x] No

## Runtime handoff fields

- Source of truth: capture store (`apire_kb/`, machine-local, gitignored)
- Allowed tools: 7 `api_re_*`; six transports; no transmission action exists
- Prohibited actions: any send/replay — tests/test_no_egress.py,
  tests/test_tool_surface.py
- Pending validations: ADR-009 re-anchor pass (above)
- Commit status: clean tree after this session's commit
