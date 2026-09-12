# Session handoff — 2026-09-12

## Session metadata

- Branch: main (initial planning commit; feature branches start with M1)
- Last commit: chore: install AI safety infrastructure (M0)
- Test status: `9 passed in 0.27s` (smoke ×6 + no-egress scan ×3)

## Current state

M0 complete: governing rule, full design docs, ADRs 000–007, canonical
schemas, CI, PR/issue templates, handoff template, smoke +
no-egress capability scan (both green). FL Studio 26.1.6.5639 Windows
installer staged at `targets/fl-studio/installers/` with pinned SHA-256
(gitignored). Engine package `apire/` does not exist yet — by design; M1
creates it test-first.

Works: nothing at runtime — this repo is design + safety infrastructure.
Broken: nothing known.

## What was done and why

New repo `mnehmos.api.re.mcp` (apire): passive API reverse engineering MCP —
observe authorized applications, never impersonate them. First commit is the
safety system per the vibe coders bible Ch18/34. Design merges: the user's
pipeline (passive capture → normalize → differential correlate → schema
induction → LLM semantic valve → evidence graph → exports incl.
mcp_candidate); remcp's architecture contracts (engine/server split, envelope
+ in-band warnings, closed provenance vocabulary with caps and deterministic
verifiers, atomic JSON KB, pinned deps, wire test); the workspace
action-enum doctrine from F:/Github/MCP_CONSOLIDATION_PLAN.md (7 tools, ≤8
actions, no Optional params); and the dual-target evaluation rig
(control reference app with planted spec discrepancy + FL Studio challenge).

## Decision log

- Evidence levels: user's six (CONFIRMED…UNKNOWN) mapped to numeric bands;
  machine values use underscores (`STRONGLY_INFERRED`).
- `llm_proposal` provenance class cap pinned at 0.00 — semantic names enter
  as zero-confidence proposals; only capture-derived classes raise claims.
- 7 tools, not the doctrine's ≤6 target: merging the semantics write valve
  into a read tool violates least-authority (ADR-005).
- Repo created at F:/Github root beside its siblings, not F:/Github/mcp/ —
  STANDARDS.md's layout table conflicts with actual sibling placement; noted
  as an open question, move with the path-update checklist later.
- Passive-only enforcement: elimination (no replay action exists) +
  engineering (AST no-egress scan, sockets confined to apire/capture/) +
  detection (tool-surface verb test) — ADR-003.

## Deferred work (with reason)

- Engine code: M1 milestone, test-first (redaction + store + file ingest).
  Nothing to build until this planning commit lands.
- reference_app + score.py: M2 (needs the proxy first to be meaningful).
- FL Studio install: not performed this session (download only, as asked);
  install is the campaign's first step in M6 or earlier if driven manually.

## Open questions

- Repo location (root vs F:/Github/mcp/) — see PROJECT_CONTEXT.md.
- HTTPS capture strategy (local CA vs DevTools attach) — ADR required
  before M4.

## Known blockers

None.

## Next step (exactly one)

Open M1 issues (redaction, capture store, file ingest) and build
`tests/test_redaction.py` red: ingest a frame containing a bearer token
through the public path and assert the stored bytes never contain it.

## CLAUDE.md changed?

- [x] No (created this session; constraints are initial)

## Runtime handoff fields

- Source of truth: capture store (not yet implemented; schemas in `schemas/`)
- Allowed tools: none registered yet (server.py lands M2)
- Prohibited actions: any transmission — enforced by tests/test_no_egress.py
- Pending validations: none
- Commit status: clean tree at M0
