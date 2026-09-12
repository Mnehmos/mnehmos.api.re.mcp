# apire — mnehmos.api.re.mcp

**Status:** working, tested (44 tests + 15-check stdio wire test, green).
M1–M4 partially landed: engine (redaction, capture store, normalizer, OSC
decoder, differential correlator, evidence KB, semantics valve), server
(7 action-enum tools), transports (`file_ingest`, `udp_observe`,
`process_meta`). First real evidence captured against live FL Studio 26.1.6
— see [targets/fl-studio/README.md](targets/fl-studio/README.md).
Exporters, WS/SSE normalizers, and the DevTools attach transport land in
M5/M6 ([docs/roadmap.md](docs/roadmap.md)).

An MCP server that reverse engineers the API surface of an authorized application
**by watching it**: it passively captures the traffic, frames, logs and bundles an
application already produces, correlates captures differentially, infers schemas,
and emits specifications (OpenAPI / AsyncAPI / JSON Schema / protocol catalog /
architecture map / candidate MCP surface) — with a deterministic evidence trail
for every claim.

It does not send requests, replay traffic, modify state, or hold any capability
that could. It does not learn credentials — credential-shaped values are
redacted or pseudonymized at ingestion, before anything touches disk. It does not
trust an LLM's interpretation: the model proposes semantic names; the evidence
store decides what they are worth.

> **Governing rule: Observe applications. Never impersonate them.**

## Pipeline

```text
AUTHORIZED APPLICATION
        |
        +-- HTTP traffic          +-- logs
        +-- WebSocket frames      +-- JS bundles
        +-- SSE                   +-- process / module metadata
        +-- local sockets
        +-- named pipes / RPC metadata
                |
                v
        Passive Capture  ->  Normalizer  ->  Differential Correlator
                ->  Schema Inference  ->  Semantic Mapper (LLM proposals,
                evidence-gated)  ->  Evidence Graph
                ->  OpenAPI / AsyncAPI / protocol catalog
                    JSON Schema / event catalog
                    architecture map
                    candidate MCP surface
```

## Design principles

1. **Observe applications. Never impersonate them.** The engine has no
   network-transmission capability by construction. No replay API exists in the
   tool surface, and a CI test fails the build if egress libraries appear in the
   engine. See [docs/security-model.md](docs/security-model.md).
2. **The model proposes; the evidence decides.** An LLM proposal carries zero
   confidence by policy (`llm_proposal` cap = 0.0). Only deterministic,
   recomputable evidence raises a claim. See [docs/evidence-model.md](docs/evidence-model.md).
3. **Redact at ingestion.** Authorization headers, cookies, tokens, session IDs
   and credential-shaped values are removed or HMAC-pseudonymized before a frame
   is persisted. The store learns `Authorization: Bearer <REDACTED>`, not the
   credential.
4. **Every claim re-derives from the capture store.** Verification is
   recomputation against captured artifacts — never trust in a model's report,
   including this tool's own past output.
5. **Captures are experiments; the human is the actuator.** The system never
   pokes the target. It asks the human to perform labeled actions ("rename a
   mixer track twice with names of different lengths") and diffs the captures.
   Active science, passive tool.
6. **Small surface, action enums.** Seven `api_re_*` tools, each an action
   enum over one domain, per the workspace action-enum doctrine
   ([MCP_CONSOLIDATION_PLAN.md]). No replay-shaped action exists to call.
7. **In-band evidence, not logging.** Responses are envelopes
   (`ok / target / method / reliability / warnings / result`) with warnings that
   state their impact — the same contract as remcp.

## Tools (planned)

| Tool | Actions | Reads/Writes |
| ---- | ------- | ------------ |
| `api_re_capture` | start, stop, status, list, label, note | capture store |
| `api_re_observations` | list, inspect, compare, correlate | capture store |
| `api_re_protocol` | transports, endpoints, messages, events, schemas, errors | evidence graph |
| `api_re_architecture` | processes, connections, services, boundaries | evidence graph |
| `api_re_evidence` | query, explain, contradictions, unknowns, experiments, policy | evidence graph |
| `api_re_semantics` | propose, attach_evidence, review, link | evidence graph (gated write valve) |
| `api_re_export` | openapi, asyncapi, json_schema, protocol_spec, architecture, mcp_candidate | files |

## Evidence levels

| Level | Confidence band | Meaning |
| ----- | --------------- | ------- |
| CONFIRMED | 0.95 – 1.00 | matches an authoritative source (published spec) or human-verified |
| OBSERVED | 0.80 – 0.95 | directly present in captured traffic; recomputable from a capture |
| STRONGLY INFERRED | 0.60 – 0.80 | corroborated across ≥ 2 independent labeled captures |
| INFERRED | 0.40 – 0.60 | pattern from a single capture (schema induction, shape families) |
| HYPOTHESIS | 0.10 – 0.40 | model proposal with weak evidence behind it |
| UNKNOWN | 0.00 – 0.10 | observed but uninterpretable |

The worked example this whole design exists for — an opaque `message type: 47`
becoming `plugin.catalog.updated` at confidence 0.91 with the exact captures that
justify it — is in [docs/evidence-model.md](docs/evidence-model.md).

## Evaluation

Two targets from day one ([docs/evaluation.md](docs/evaluation.md)):

- **Control:** a locally-run application with a committed, published OpenAPI
  spec. The benchmark scores reconstructed endpoints/schemas against ground
  truth (precision/recall). If the tool cannot reconstruct a *documented* API
  honestly, nothing else matters.
- **Challenge:** FL Studio — opaque, native, currently inaccessible surfaces.
  Success is a useful semantic map plus an evidence trail a human can audit,
  not a score.

## Layout

```text
mnehmos.api.re.mcp/
  README.md, CLAUDE.md, AGENTS.md, PROJECT_CONTEXT.md, CONTRIBUTING.md
  server.py              (M2 — FastMCP wiring, action-enum dispatch, envelope)
  apire/                 (M1+ — engine package: zero MCP imports, zero egress)
  schemas/               (canonical contracts: capture, frame, observation,
                          evidence link, semantic proposal, envelope)
  docs/                  (architecture, security-model, evidence-model,
                          tool-surface, roadmap, evaluation, decisions/)
  targets/               (dogfooding: control app + FL Studio campaign notes)
  tests/                 (smoke + no-egress capability scan + engine tests)
  .agent/                (session handoffs)
  .github/               (CI, PR and issue templates)
```

## Registration

```json
{
  "apire": {
    "command": "python",
    "args": ["F:\\Github\\mnehmos.api.re.mcp\\server.py"],
    "description": "Passive API reverse engineering. Observe applications, never impersonate them."
  }
}
```

Pin the absolute interpreter the same way remcp does: a bare `python` that lacks
the pinned deps dies at import.

## License

MIT — see [LICENSE](LICENSE). Read-only by design; see
[docs/security-model.md](docs/security-model.md) for what that means in
enforcement terms, not adjectives.

[MCP_CONSOLIDATION_PLAN.md]: F:/Github/MCP_CONSOLIDATION_PLAN.md
