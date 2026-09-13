# Session handoff — 2026-09-12 (build-out session: M5 + M2 + benchmark + transports)

## Session metadata

- Branch: main
- Last commit: M2 remainder + control benchmark + log_tail + ADR-008
- Test status: `71 passed` (pytest, incl. the control benchmark in CI) and
  `17 passed, 0 failed` (tests/wire_test.py)

## Current state

Everything in the roadmap is now landed except the items listed under
"Blocked / deferred" below:

- **M5 exporters** (committed f625529): openapi, asyncapi, json_schema,
  protocol_spec, architecture, mcp_candidate — per-element `x-apire`
  evidence, `min_level` floors with speculative sections, no-secret audit.
  FL specimen committed at `targets/fl-studio/exports/mcp_candidate.json`.
- **M2 loopback proxy**: `apire/capture/http_proxy.py`, 6 tests (relay both
  ways, redaction passthrough, CONNECT refused, 502, chunked intact).
  Body-aware induction: responses now induct from decoded JSON bodies;
  OpenAPI/JSON Schema carry response-body schemas.
- **Control benchmark**: `targets/control/reference_app/` + `score.py`,
  running in CI. First results: endpoint recall/precision 1.000, method
  accuracy 1.000, schema property P/R 0.75/0.75 (the missing quarter is the
  planted `created_at`/`created_ts` discrepancy, correctly flagged), zero
  secrets. `tests/test_benchmark.py` gates it.
- **log_tail** transport + tests (follows from end, truncation-safe).
- **Named pipes reframed (ADR-008)**: `pipe_listen` removed from the
  vocabulary — a pipe can only be read by its server, so passive
  interception is impossible without injection. Pipe *names/presence* are
  observed via `process_meta` (new `named_pipes` + `pipe_present` events).
- **no-egress scanner made precise**: `urllib.parse` no longer flagged
  (pure parsing); `from urllib import request` now correctly flagged; a
  dedicated precision test pins both directions.

## Decision log

- Response observations induct from the decoded body, `status` stripped
  from body schemas (it is transport, and it was polluting precision).
- The proxy enforces `Connection: close` hop-by-hop; CONNECT is refused and
  recorded (an opaque tunnel is unobservable — refuse, don't pretend).
- `_Reader` exists because the first proxy implementation lost body bytes
  between head and body reads — caught by tests, recorded in the module
  docstring.
- The benchmark scores the *response body* def for schema metrics; request
  defs remain for request-shape evidence.

## Blocked / deferred (with reason)

- **OSC (FL H1)**: requires in-app GUI enablement — human step.
- **`Network.getResponseBody`** for devtools_attach: next upgrade; would let
  the evidence settle the Unleash-vs-frontend_config rival readings.
- **WS/SSE dedicated normalizers**: WS frames already traverse the pipeline
  (devtools_attach stamps ws_url); SSE arrives via proxy body samples.
  Nothing blocks on this; revisit when a target actually uses SSE.
- **Ecological control tier** (open5e-api/Gitea): M5+ optional tier.
- **FL campaign audit session**: a fresh session should attack the
  STRONGLY_INFERRED+ FL claims before any of them is presented as settled.

## Known blockers

None technical.

## Next step (exactly one)

Implement `Network.getResponseBody` capture (opt-in, size-capped) in
`devtools_attach`, then re-run the FL-Cloud load capture and check whether
the Unleash-vs-config contradiction resolves by response shape.

## CLAUDE.md changed?

- [x] No

## Runtime handoff fields

- Source of truth: capture store (`apire_kb/`, machine-local, gitignored)
- Allowed tools: 7 `api_re_*`; transports are the six in
  `apire/capture/__init__.py`; no transmission action exists
- Prohibited actions: any send/replay — enforced by tests/test_no_egress.py
  (now module-path precise) and tests/test_tool_surface.py
- Pending validations: FL claim audit (above)
- Commit status: clean tree after this session's commit
