# CLAUDE.md — mnehmos.api.re.mcp (apire)

Passive API reverse engineering MCP server. **Observe applications. Never
impersonate them.**

## The constraint (read before generating anything)

This tool is **passive by construction**. Every change is checked against it:

1. **No transmission capability.** The engine (`apire/`) must never originate
   application-semantic requests: no replay, no request execution, no sending
   observed credentials anywhere. Listening, accepting inbound connections from
   the observed application, and responding to the app inside a sanctioned
   passthrough transport are allowed; originating requests to application
   endpoints is not. `tests/test_no_egress.py` scans the engine AST and fails
   the build on banned egress imports/calls. Never weaken it.
2. **Redact at ingestion.** Credential material is removed or pseudonymized
   before persistence. Code that writes frames to the store without passing the
   redaction gate is a defect regardless of tests passing elsewhere.
3. **The model proposes; evidence decides.** `llm_proposal` provenance carries
   cap 0.0. Semantic names enter only through `api_re_semantics` and gain
   confidence only from deterministic, recomputable corroboration in the
   capture store. Never add a code path where an LLM claim becomes stored truth
   without passing the evidence policy.
4. **Every claim re-derives.** Verifiers recompute from capture artifacts. A
   verifier that trusts a previous result (including its own output) is broken
   by definition.

## Project

- Name: apire (repo `mnehmos.api.re.mcp`)
- One sentence: reconstruct an authorized application's API surface from passive
  observation, with a deterministic evidence trail for every claim.
- Not: a pentest proxy, a traffic generator, a credential harvester (the
  opposite — redaction is upstream of disk), or a MITM exploit framework.

## Verification commands

- `pytest` — full suite (smoke, capability scan, engine tests)
- `python -m pytest tests/test_no_egress.py -q` — the passive-only scan alone
- `python server.py` — manual MCP smoke over stdio (from M2)

A change is not done until its verification command has been run and the output
pasted into the handoff.

## Architecture rules

- `apire/` is a pure library: zero MCP imports, typed errors only, never calls
  `SystemExit`, no logging — in-band envelope warnings instead (remcp contract).
- `server.py` is the only MCP layer: action-enum dispatch tools, the `@tool`
  exception wrapper, envelope serialization, response clipping.
- Action-enum tool surface per `F:/Github/MCP_CONSOLIDATION_PLAN.md`: ≤ 8
  actions per tool, optional params get plain defaults (never `Optional`, which
  emits `anyOf` that strict providers reject).
- Storage: append-only capture store (content-addressed raw frames) + atomic
  JSON KB with one-generation `.bak` (remcp `kb.py` contract). Evidence stores
  never leave the machine; they are gitignored by default.
- Pin dependencies exactly in `requirements.txt` with a rationale comment.

## Boundaries

- No secrets in code, config, tests, fixtures, or captures. Captured traffic
  fixtures are synthetic or scrubbed; assume any real token in a fixture is a
  leaked secret.
- No destructive commands. No weakening tests to make them pass. No scope
  mixing: one issue per branch.
- New work starts from an issue with acceptance criteria. Branch
  `type/short-description-issue-number`. First commit of any new capability is
  the failing test.
- Captured evidence directories (`apire_kb/`, `captures/`) are gitignored;
  never commit them, never commit anything under `targets/*/installers/`.

## Model role

Runtime capability. The calling LLM drives the tool loop and proposes semantic
interpretations; deterministic code owns capture, redaction, correlation,
schema induction, evidence verification, and exports. Per-tool role cards:
[docs/decisions/001-model-role-card.md](docs/decisions/001-model-role-card.md).
The weights/specification/verdict split for this project is in
[docs/decisions/002-weights-specification-verdict.md](docs/decisions/002-weights-specification-verdict.md).

## Close of session

Clean tree, full `pytest` run, `.agent/handoff.md` written from
`.agent/handoff-template.md`, CLAUDE.md updated if any constraint above
changed, push the branch. Write the handoff as if the next agent has never
heard of this project.

> A rule that lives only in this prompt is a hope. The rules above are enforced
> by `tests/test_no_egress.py`, the evidence policy in `apire/kb.py` (when it
> exists), and CI. Move rules up the hierarchy whenever you can; do not leave
> them here.
