# AGENTS.md — operating model for AI sessions

Applies to every agent (human or model) that modifies this repository.

## Operating model

- Treat every change as a **proposal** crossing a **commit boundary**. Intent
  becomes real only after it crosses; only validated state becomes real.
- Small diffs. One commit, one reason. Do not invent scope. Read CLAUDE.md and
  the latest `.agent/handoff.md` before generating.
- Issue-first: every change starts from an issue stating what changes, why, and
  verifiable acceptance criteria. Anything outside the issue is out of scope.
- Test-first: write the test, run it, watch it fail (red), implement (green),
  refactor. A bug fix lands in the same commit as the regression test that
  fails without it. Never let an agent fix a bug it cannot reproduce.
- Do not ask the agent to build a feature until the feature has a shape: input
  schema, source of truth, validator chain, state transition, trace event,
  user-visible fallback.

## Validation commands

| Command | Checks |
| ------- | ------ |
| `pytest` | full suite |
| `python -m pytest tests/test_no_egress.py -q` | passive-only capability scan |

Paste actual output into the PR/handoff. Paraphrased evidence is no evidence.

## Boundaries

- No secrets anywhere in the repo (see `.gitignore` secrets block; run the
  STANDARDS.md secret grep before first push).
- No destructive commands against the observed target. This tool observes; it
  does not act on applications. A change that adds transmission capability is
  rejected on sight, not debated.
- No weakening of tests, schemas, or the evidence policy. No scope mixing.
- Do not commit capture stores, installers, or anything under `apire_kb/`,
  `captures/`, `targets/*/installers/`.

## Delegation contract

Any task delegated to a subagent must carry: Goal, Scope, Out of scope,
Constraints, Validation command, Expected handoff. Subagent output is a
proposal and passes the same gates as any other generation. A generator never
verifies its own work; verification is structural (recompute from artifacts,
or a deliberately independent check), not a re-read.

## Handoff report (end of session)

1. Branch and last commit.
2. Test status (real output).
3. What was done and why; decision log with reasons.
4. Deferred work, with reason.
5. Open questions; known blockers.
6. Exactly one next step.
7. Whether CLAUDE.md changed.

Write it as if the next agent has never heard of this project.
Template: `.agent/handoff-template.md`.
