# Targets — the dual-target dogfooding rig

Every capability is proven here before it is claimed anywhere
([docs/evaluation.md](../docs/evaluation.md), ADR-006).

| Directory | Role | Ground truth |
| --------- | ---- | ------------ |
| [control/](control/) | documented reference application | committed OpenAPI spec + scripted WS/SSE behavior |
| [fl-studio/](fl-studio/) | opaque challenge application | none — success is an audited evidence trail |

Rules for both:

- Capture stores and installers under `targets/*/` are machine-local and
  gitignored. Nothing observed ever gets committed.
- Each observation session starts from an issue stating its hypothesis and
  the labeled actions the human will perform.
- The tool observes. The human acts. Nothing in this directory automates the
  target application into doing anything.
