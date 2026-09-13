# Evaluation — the dual-target benchmark

A cool RE demo proves nothing; an evaluation benchmark does. From M2 onward,
every capability is measured against a **control target with published ground
truth** before it is pointed at the **challenge target** that has none.

## Control target: documented application

A locally-run application whose API is documented. Two tiers:

1. **Reference app** (M2, deterministic): `targets/control/reference_app/` —
   a small local application (FastAPI-based) with a *committed* `openapi.json`
   plus known WS/SSE behavior. It exists to be observed: realistic auth
   headers (so redaction is exercised), a WebSocket event stream, pagination,
   polymorphic payloads, at least one endpoint documented *wrong* on purpose
   (the tool should report the contradiction between `authoritative_spec` and
   `captured_traffic` — the highest-value test in the benchmark).
2. **Third-party app** (M5+, ecological): a real open-source service with a
   published spec (candidates already in the workspace: `open5e-api`,
   Gitea, etc.). Same scoring, messier reality.

## First results (2026-09-12, control target)

`python targets/control/score.py` — deterministic, runs in CI as
`tests/test_benchmark.py`:

| Metric | Result |
| ------ | ------ |
| Endpoint recall | **1.000** (7/7 documented endpoints reconstructed) |
| Endpoint precision | **1.000** |
| Method accuracy | **1.000** |
| Schema property precision / recall | 0.750 / 0.750 (the missing 0.25 *is* the planted discrepancy) |
| Spec discrepancy flagged | **yes** — the reconstruction emitted `created_ts: number` and flagged `created_at` absent, following behavior over documentation |
| Secrets leaked | 0 |
| Frames recorded | 20 (10 requests / 10 responses across a 10-call scripted session) |

The instrument measures. The challenge target (FL Studio) results are in
[targets/fl-studio/README.md](../targets/fl-studio/README.md).

## Ecological tier (built 2026-09-12)

A real third-party application with a published spec it does not coordinate
with us about: **Gitea** (single binary, sqlite — chosen for runnability).
`targets/control/ecological/` has the recipe (`run_gitea.cmd`) and the
scorer (`score_ecological.py`). First results: endpoint precision 0.500
(4 observed paths; two honest misses documented), version schema agreement
1.000, secrets 0 — and **two real engine defects found and fixed on the
first run** (the proxy sent no Host header upstream; credentials inside
JSON-string bodies were not redacted). This tier is not in CI (it needs the
binary); run it manually when touching transports or redaction.

### Scoring (computed by `targets/control/score.py`, not by an LLM)

| Metric | Definition |
| ------ | ---------- |
| Endpoint recall | reconstructed endpoints ∩ ground truth / ground truth |
| Endpoint precision | reconstructed endpoints that exist in ground truth / reconstructed |
| Method accuracy | exact (method, path) matches / matches |
| Schema property P/R | per-endpoint property name + type agreement vs spec |
| Event fidelity | WS/SSE events reconstructed vs emitted during the scripted session |
| Contradiction detection | the planted doc-vs-behavior discrepancy is reported |
| Semantic name agreement | proposed names vs the spec's own operationIds (exact / normalized fuzzy) |

**Hard gates, binary, on every run:**

- `secrets_leaked = 0` — fixture credentials appear nowhere in the store,
  exports, or logs.
- `egress_incidents = 0` — the no-egress scan passes; the proxy originated
  nothing beyond passthrough (asserted by a canary endpoint the proxy must
  never request).
- `unearned_confidence = 0` — no claim exceeds its provenance caps; no
  `llm_proposal`-only claim sits above HYPOTHESIS.

Reporting is a table per milestone tag; regressions block the release tag.

## Challenge target: FL Studio

Opaque, native, no usable public API documentation. The benchmark here is
not a score — it is an audited demonstration:

1. **Install + inventory.** FL Studio 26.1.6 Windows installer staged at
   `targets/fl-studio/installers/` (gitignored). Install as trial (the trial
   is the full version; licensing is irrelevant to observation). Inventory
   processes, modules, pipes, sockets via `process_meta`.
2. **Transport hypothesis sessions.** Each session states its hypothesis
   *before* capture (issue-first discipline applies to RE sessions):
   - H1: local OSC traffic (FL Studio has an OSC server) is observable and
     correlates with UI actions.
   - H2: MIDI-scripting host exposes a scripting bridge surface.
   - H3: plugin bridge processes exchange structured messages over
     pipes/shared memory. (Reframed by ADR-008: bridge existence and pipe
     naming are observable through `process_meta`; message interception is
     not, without an operator-configured pipe endpoint.)
   - H4: project file operations are mirrored in observable IPC.
3. **Differential sessions.** Human performs labeled action batteries (open
   project / select channel / rename channel ×2 with different lengths / open
   plugin browser / scan plugins). The correlator + semantics valve produce
   the semantic map; every claim carries its captures.
4. **Audit.** A fresh reviewer session (not the session that built the map)
   runs `api_re_evidence explain` on every STRONGLY INFERRED+ claim and tries
   to break it with `contradictions`. The map is accepted only if the auditor
   fails.

**Success criteria for the campaign:** a semantic map of ≥ 20 correlated
observations with ≥ 5 STRONGLY INFERRED+ claims that survive audit, and an
`mcp_candidate` export a human judges worth turning into a real MCP
(the `FL Studio MCP` arm of the capability foundry).

## What this benchmark is for

It is the difference between "the model guessed well" and "the instrument
measures". The control target proves the instrument; the challenge target
proves the instrument on darkness — and every result arrives with the
evidence that makes it checkable by the next agent, human or model.
