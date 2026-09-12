# Contributing

## Ground rules

1. Read `CLAUDE.md` and the newest `.agent/handoff.md` before generating.
2. Every change starts from an issue: what, why, acceptance criteria, out of
   scope.
3. Branch before generation: `type/short-description-issue-number`
   (`feature/differential-correlator-12`). Never commit to `main` directly.
4. Test-first. Watch the test fail before implementing. Regression tests ride
   in the same commit as the fix they pin.
5. Commit format: `type: short description` + body explaining the why, what was
   rejected, and what the next session needs to know. Write the body for the
   model that reads `git log` next.
6. Full `pytest` green before every commit; paste evidence in the PR.

## Project-specific invariants (reject on sight)

- Any engine change that adds an outbound request capability (see
  `tests/test_no_egress.py` — do not weaken the ban list to pass).
- Any path where credential material persists to disk.
- Any path where an LLM proposal gains stored confidence without passing the
  evidence policy (`llm_proposal` cap = 0.0).
- Any `Optional[...]` parameter in a tool signature (emits `anyOf`; use plain
  defaults per the action-enum doctrine).

## Session close

Clean tree, full suite green, `.agent/handoff.md` written, CLAUDE.md updated if
a constraint changed, push.
