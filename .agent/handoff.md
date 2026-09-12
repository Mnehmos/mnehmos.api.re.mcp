# Session handoff — 2026-09-12 (implementation session)

## Session metadata

- Branch: main (single-developer repo; feature branches begin at next issue)
- Last commit: feat: M1–M4 engine + M2 server, dogfooded on FL Studio
- Test status: `44 passed` (pytest, full suite) and `15 passed, 0 failed`
  (tests/wire_test.py, stdio end-to-end)

## Current state

Working now, verified by the commands above:

- Engine: redaction gate, capture store (append-only manifests + atomic KB),
  normalizer with per-entity canonical keys, OSC decoder, differential
  correlator (exclusivity/periodicity/candidates + instrument-mismatch
  guard), evidence KB (caps, corroboration, recomputing verifiers,
  contradictions, unknowns), semantics valve (propose/attach_evidence).
- Server: 7 action-enum tools; `file_ingest`, `udp_observe`, `process_meta`
  transports live; other transports/actions return typed `unsupported`.
- Dogfood: FL Studio 26.1.6 installed (`F:\FL Studio`, silent NSIS) and
  observed; 883-frame detailed snapshot `cap_639ad53b1d8c`; 2 semantic
  claims at INFERRED 0.40 with verified provenance.

Broken: nothing known. Not yet built: exporters (M5), WS/SSE normalizers,
`devtools_attach`/`http_proxy`/`pipe_listen`/`log_tail` transports.

## What was done and why

Built M1–M4 test-first (redaction/store/OSC red first, then green) and M2
(server + wire test with deliberate failure paths). Dogfooded on FL Studio
per the challenge-target protocol. Details and the exact evidence trail are
in CHANGELOG.md (0.1.0) and targets/fl-studio/README.md.

## Decision log

- A bare proposal (confidence 0.0) is level `UNKNOWN`, not `HYPOTHESIS`: an
  unsupported guess explains nothing and must not remove an observation from
  `unknowns`. Doc + tests updated to match (this replaced the earlier
  "band floor = HYPOTHESIS" wording).
- process_meta emits per-entity frames (v2) alongside summary frames: the
  canonical key must name the entity ("process FL64.exe"), or differential
  correlation cannot distinguish apps. Instrument version is recorded per
  capture; the correlator flags cross-version comparisons as unreliable.
- Correlation caps output (200 exclusivity rows, 100 candidates) to keep
  responses inside context budgets.
- `attach_evidence` added to api_re_semantics (4 actions): the valve needs a
  documented entry for capture-derived evidence; docs/tool-surface.md
  updated. Rejected hiding it inside `review` (would merge read and write).

## Dogfood findings (FL Studio)

- `FL64.exe` main process; **WebView2 embedded** (`msedgewebview2.exe`
  child) → FL 26's UI is Chromium; `devtools_attach` (M6) is the viable
  passive transport (`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=
  --remote-debugging-port=9222` at launch, a human decision).
- OSC is **off** by default (no UDP sockets; no OSC config in registry;
  empty remote-scripts folder). H1 requires an in-app enable step.
- The instrument confound (v1 vs v2 captures) produced fake exclusivity
  answers; guard added, and the baseline must be re-taken with v2 before any
  further differential claims. See targets/fl-studio/README.md recipes.

## Deferred work (with reason)

- Baseline re-take with FL closed: needs FL closed; FL is currently running
  on the user's desktop (left running deliberately — it is their session).
- OSC enablement: in-app GUI step, human-in-the-loop.
- Exporters (M5): next milestone after the baseline re-take; the graph must
  carry levels through projections first.

## Open questions

- Whether FL's WebView2 traffic is high-value (UI API surface) or mostly
  static assets — answer with the M6attach transport, not speculation.
- Does FL's OSC config live only in-app, or in a config file after first
  enable? Re-check the registry diff after the human enables OSC.

## Known blockers

None technical. The differential demo is data-blocked on the baseline
re-take (FL currently running).

## Next step (exactly one)

When FL Studio is closed: capture process_meta v2 ×2 labeled `FL absent`,
relaunch FL, capture ×2 labeled `FL present`, then
`api_re_observations correlate` — confirm the candidates are FL-specific
and NOT `svchost.exe`-style instrument artifacts, and record the result in
targets/fl-studio/README.md.

## CLAUDE.md changed?

- [x] No

## Runtime handoff fields

- Source of truth: capture store (`apire_kb/`, machine-local, gitignored)
- Allowed tools: the 7 `api_re_*` tools; no transmission action exists
- Prohibited actions: any send/replay — enforced by tests/test_no_egress.py
  and tests/test_tool_surface.py
- Pending validations: baseline re-take (above)
- Commit status: clean tree after this session's commit
