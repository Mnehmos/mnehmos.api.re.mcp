# Session handoff — 2026-09-12 (autonomous FL Studio campaign)

## Session metadata

- Branch: main
- Last commit: feat: FL Studio campaign — differential proof, devtools_attach,
  first cloud-API map
- Test status: `51 passed` (pytest) and `15 passed, 0 failed`
  (tests/wire_test.py)

## Current state

Working and verified:

- All of 0.1.0, plus `devtools_attach` (DevTools/WebView2 attach transport)
  with parser tests, a raw-HTTP client test, and a live attach test.
- FL Studio campaign results (details + ids: targets/fl-studio/README.md,
  CHANGELOG 0.1.1):
  - Differential proof under matched instruments (process_meta/v2): 144
    FL-exclusive candidates, reliability=sound, no confounds.
  - Passive observation of FL's embedded Chromium (FL-Cloud grid): cloud
    endpoints observed, 10 semantic claims at INFERRED 0.40 with verified
    `captured_traffic` provenance; one rival-reading pair linked as
    contradictions.
  - Redaction exercised on live traffic: 4 Authorization headers + 33
    credential-shaped values + 14 sensitive keys, zero leaks (manifest
    audit).

Broken: nothing known. FL Studio is currently running (relaunched by this
session with the debug port enabled).

## What was done and why

The user delegated autonomous operation ("no human in the loop"). Executed:
baseline re-take (close FL → absent captures → relaunch → present captures),
correlation, CDP reconnaissance, `devtools_attach` implementation (two live
defects found and fixed: keep-alive HTTP parsing, Origin-header rejection),
and a live FL-Cloud load capture followed by the semantics valve.

## Decision log

- Attach before navigation: the transport polls /json/list at 0.25s and
  attaches to a page target as soon as it exists (about:blank), so the load
  sequence is captured. Learned the hard way in the first attempt, which
  attached to a doomed instance.
- Response observations now carry `HTTP <status> <path>` labels; without
  them the response side of the graph was ungroupable.
- Unleash rival reading: `/api/frontend` was proposed as
  `flstudio.cloud.feature_flags` (the evidence names an Unleash host), kept
  alongside the earlier `frontend_config` reading as linked contradictions
  rather than overwriting. Revision-by-contradiction demonstrated on real
  data.
- `$LAST_CAPTURE`/`$LAST_CLAIM` chaining added to the dogfood client instead
  of adding stateful tool parameters to the MCP surface.

## Deferred work (with reason)

- Response bodies (`Network.getResponseBody`): needed to settle the
  feature_flags-vs-config rivalry; next transport upgrade.
- Next.js `/_next/data/<buildId>/` path-template collapse: build-id segment
  varies, routes do not group yet (normalizer rule needed).
- OSC (H1): requires in-app GUI enablement — human step, explicitly out of
  scope for autonomous operation.
- Exporters (M5): still pending; the graph should carry
  `evidence_level` through projections first (partially done in
  `apire/project.py`).

## Open questions

- Which cloud endpoints require the authenticated session (only the Unleash
  host showed Authorization; the trial may be partially authenticated)?
- Does FL-Cloud use WebSockets at all? Zero ws_frame observations in an
  80s idle window (possibly load-only traffic).

## Known blockers

None. FL is running; killing/relaunching it is safe (fresh trial, no user
work in it).

## Next step (exactly one)

Add `Network.getResponseBody` capture (opt-in, size-capped) to
`devtools_attach`, then re-run the FL-Cloud load capture to settle the
feature_flags-vs-frontend_config contradiction with response-shape evidence.

## CLAUDE.md changed?

- [x] No

## Runtime handoff fields

- Source of truth: capture store (`apire_kb/`, machine-local, gitignored)
- Allowed tools: 7 `api_re_*`; no transmission action exists
- Prohibited actions: any send/replay — enforced by tests/test_no_egress.py
  and tests/test_tool_surface.py
- Pending validations: `Network.getResponseBody` upgrade (above)
- Commit status: clean tree after this session's commit
