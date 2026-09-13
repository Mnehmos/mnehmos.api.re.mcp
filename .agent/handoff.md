# Session handoff — 2026-09-12 (completion pass: everything remaining)

## Session metadata

- Branch: main · pushed to private origin
  (https://github.com/Mnehmos/mnehmos.api.re.mcp)
- Last commit: ecological tier (6af3e52) + this docs commit
- Test status: `89 passed` (pytest) · `22 passed, 0 failed` (wire test)

## Current state — the tracked work list is empty

Everything that was tracked as remaining or deferred is done:

- **All six previously-refused actions implemented** (protocol
  events/schemas/errors, architecture services/boundaries,
  evidence.experiments). No action on any tool refuses anymore.
- **ADR-009 implemented**: host in HTTP keys (normalizer v2), KB records
  `normalizer_version`, live KB migrated by `scripts/reanchor_v2.py`
  (9 moved / 1 skipped-honest / 0 failed), broken claims flagged by
  `explain`.
- **Store fails closed** on concurrent sessions (a real clobbering incident
  became the guard + regression test).
- **Body-fetch cap** 2 MB → 8 MB (`APIRE_MAX_BODY_FETCH`).
- **Ecological tier built and run** (Gitea 1.27.3): found two real engine
  defects on first contact — proxy sent no Host header; JSON-string bodies
  bypassed redaction — both fixed with regression tests.
- Repo pushed to a **private** GitHub remote per STANDARDS.

## Deliberately not done (with reasons, not excuses)

- **Normalizer v3 two-sighting rule** for word-like path segments
  (`/users/<name>` stays literal until two different values are observed).
  This is a key change ⇒ re-anchor pass; queue it with the reanchor script,
  don't rush it.
- **MCP client registration** in ZCode/CLI configs: left opt-in because of
  the registered-tool ceiling tracked in MCP_CONSOLIDATION_PLAN.md. The
  README has the JSON block.
- FL campaign: response bodies settled the Unleash-vs-config rivalry
  (feature_flags @ STRONGLY_INFERRED 0.70); H1 (OSC) was falsified with
  recorded evidence. No open FL threads.

## Notes for the next session

- Gitea (ecological target) and FL Studio were left running by this
  session; stop with `taskkill /IM gitea.exe /F` and
  `taskkill /IM FL64.exe /F` respectively (FL carries no debug port
  requirements now).
- The evidence KB (`apire_kb/`, gitignored) is machine-local and now on
  normalizer v2 with 13 claims, three at STRONGLY_INFERRED.
- `targets/fl-studio/operator_gui.py` + `ocr.ps1` are operator tooling
  (human role, automated) — not part of the engine; pyautogui is
  deliberately not a server dependency.

## CLAUDE.md changed?

- [x] No

## Runtime handoff fields

- Source of truth: capture store (`apire_kb/`)
- Allowed tools: 7 `api_re_*`, all actions live; six transports
- Prohibited actions: any send/replay — enforced by tests/test_no_egress.py
  and tests/test_tool_surface.py
- Pending validations: none
- Commit status: clean tree after this commit, pushed
