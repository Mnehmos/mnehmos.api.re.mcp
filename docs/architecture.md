# Architecture

```text
AUTHORIZED APPLICATION (user-authorized inspection target)
        |
        +-- HTTP traffic          +-- logs
        +-- WebSocket frames      +-- JS bundles (files)
        +-- SSE                   +-- process / module metadata
        +-- local sockets
        +-- named pipes / RPC metadata
                v
        [1] Passive Capture   -- transports listen; they never originate
                v                application requests
        [2] Redactor          -- runs BEFORE persistence (elimination tier)
                v
        [3] Capture Store     -- append-only, content-addressed raw frames
                v
        [4] Normalizer        -- per-protocol -> common Observation IR
                v
        [5] Differential Correlator -- labeled capture spans vs each other
                v
        [6] Schema Induction  -- shape families, type lattice, templates
                v
        [7] Semantic Mapper   -- LLM proposals only; zero-confidence intake
                v
        [8] Evidence Graph    -- claims, provenance, deterministic verifiers
                v
        [9] Exporters         -- OpenAPI / AsyncAPI / JSON Schema / protocol
                                catalog / architecture map / mcp_candidate
```

First principle: **the pipeline is one-way and each stage can only read the
stage before it.** Nothing in stages 1–6 and 8–9 knows an LLM exists. Stage 7
is a valve, not a stage: proposals enter the evidence graph through the same
policy gate as any other claim, carrying cap 0.0.

## Module layout (mirrors remcp)

| Module | Responsibility |
| ------ | -------------- |
| `apire/errors.py` | `ApiReError` base (`code`, `message`, context kwargs, `to_dict()`) + subclasses: `CaptureError`, `TransportError`, `RedactionError`, `NormalizationError`, `PolicyError`, `StoreError`, `UnsupportedError`, `ExportError`. Library never calls `SystemExit`. |
| `apire/evidence.py` | `Warning_` (`code`, `detail`, `impact`), `Envelope` (`ok/target/method/reliability/warnings/result`), reliability tri-state `sound/degraded/unreliable` — the remcp contract, unchanged. |
| `apire/redaction.py` | Ingestion scrubber (see security-model). Pure functions: `(frame_dict, mode, salt) -> frame_dict` + `redaction_report()`. |
| `apire/store.py` | Capture store: append-only JSONL manifests + content-addressed frame blobs (sha256[:16] naming, atomic writes, `.bak` on KB JSON). Evidence stores are machine-local. |
| `apire/capture/` | Transport listeners, one module per transport: `http_proxy.py` (loopback passthrough), `log_tail.py`, `file_ingest.py` (HAR/logs), `udp_observe.py` (OSC), `process_meta.py` (process/module/socket/pipe snapshots), `devtools_attach.py` (WebView2/Chromium CDP). The *only* modules allowed to touch I/O, under the connect policy of ADR-003; `pipe_listen` was removed by ADR-008 (no passive pipe interception exists). |
| `apire/normalize.py` | Frames → the common IR (`Observation`) with a canonical shape key; body-aware schema induction (decoded JSON bodies, not transport shells); per-entity keys for process/module/socket/pipe/connection events. |
| `apire/correlate.py` | Differential correlator (below). Deterministic, no clock gambits: ordering uses monotonic frame indices within captures, UTC timestamps across them. |
| `apire/schema.py` | Type-lattice merge (`integer` ∧ `number` → `number`…), constant-field detection → template, requiredness from observation counts, enum induction from small closed value sets. |
| `apire/semantics.py` | The intake valve for LLM proposals. Stores the proposal verbatim with `llm_proposal` provenance (cap 0.0). Can *never* be the sole basis of confidence. |
| `apire/kb.py` | Evidence KB: closed provenance vocabulary with caps + verifiers (remcp `kb.py` contract: policy violations raise `PolicyError` and the write is rejected). |
| `apire/graph.py` | Claim graph: subjects (observations/endpoints/messages), claims, provenance links, contradictions, unknowns. |
| `apire/export/` | `openapi.py`, `asyncapi.py`, `json_schema.py`, `protocol_spec.py`, `architecture.py`, `mcp_candidate.py`. Export = projection of the evidence graph; every emitted element carries `evidence_level`, `confidence`, and the capture IDs that justify it. Elements below a floor (default INFERRED) are emitted in a separate `speculative` section, not silently mixed in. |
| `server.py` | FastMCP wiring: seven action-enum tools, `@tool` wrapper (typed errors → JSON, clipped responses), memoized store handles. Zero business logic. |

## Core data shapes (canonical schemas in `schemas/`)

- **Capture** — a labeled, bounded observation span: `{capture_id, session_id,
  label, hypothesis, authorization_statement_fingerprint, transport,
  started_utc, ended_utc, frame_count, frames_sha256}`. The label is the
  experimental condition ("idle", "opened plugin browser") supplied by the
  human via `api_re_capture label`.
- **Frame** — raw normalized unit: `{frame_id, capture_id, seq (monotonic),
  ts_utc, direction, transport, channel, redacted_payload, payload_sha256,
  raw_ref}`. Content-addressed; immutable; append-only.
- **Observation** — deduplicated normalized fact: `{observation_id,
  kind (http_request | http_response | ws_frame | sse_event | pipe_message |
  log_line | bundle_symbol | process_meta), transport, endpoint_template,
  canonical_key, shape (induced), first_seen/last_seen, capture_refs[],
  observation_count}`. `canonical_key` = hash over (kind, transport, method,
  endpoint template, payload shape signature) — this is the unit the
  correlator diffs.
- **EvidenceLink** — `{claim_id, subject, claim, level, confidence,
  provenance[], history[], verified_records[]}` (remcp symbol shape, renamed
  for this domain).
- **SemanticProposal** — `{subject, proposed_name, rationale, evidence_refs[]}`
  as submitted by the model. Policy pins its confidence contribution at 0.

## Differential correlation (the killer capability)

Inputs: a set of captures with human labels (conditions). Per capture set, the
correlator computes, per `canonical_key`:

- **exclusivity** — appears in captures with condition X, never in captures
  without it. `exclusivity = for_condition(n) / total(n)`; the report shows
  `18/18`, `7/7`, `6/6` exactly as the worked example demands.
- **temporal adjacency** — within captures where it appears, its position
  relative to labeled action markers and to other observations: `follows`,
  `precedes`, `within_window_of`. A follow relation needs support in ≥ 2
  captures before it can reach STRONGLY INFERRED.
- **periodicity** — interval statistics; frames arriving at regular intervals
  across *all* captures (heartbeats, clocks, telemetry) are classified
  `periodic` and excluded from exclusivity claims. Noise becomes evidence of
  its own kind instead of poisoning the diff.
- **payload invariance** — which fields are constant across all sightings
  (template constants) vs variable (parameters), feeding schema induction.
- **field discrimination** — when the human runs a *designed experiment* ("rename
  a mixer track twice with names of different lengths"), the correlator finds
  fields whose variance explains the manipulation (length-correlated field →
  inferred name field). This is active science with a passive tool: the human
  is the actuator, the tool is the instrument.

Outputs are claims in the evidence graph with provenance
(`differential_exclusive`, `temporal_correlation`, `periodic_noise`,
`cross_capture_corroboration`), each recomputable from the store.

### Worked example (the design target)

After 20+ captures of an opaque DAW-like application:

```text
Observation: ws message {type: 47, ...}         (observed 31 times)
Claim (proposal):  semantic name = plugin.catalog.updated   [llm_proposal, cap 0.0]
Evidence raising it:
  differential_exclusive   18/18 plugin-scan captures   verified (recomputed)
  temporal_correlation     follows plugin-scan marker, 14 captures, >= 2 required
  payload_shape            {plugins: [...], revision: int} — plugin-id-shaped values
  counter_evidence         2 captures where type 47 preceded a *removal* -> claim
                           stays below STRONGLY INFERRED until explained, and the
                           contradiction is queryable via api_re_evidence contradictions
Result: STRONGLY INFERRED, confidence 0.78 — and the model that sees this in
api_re_evidence query knows exactly why it is not 0.91.
```

The system shows its work or it does not make the claim.

## Connect policy (transports)

Transports either **listen** (app connects to us: loopback proxy, named-pipe
server, log tail, file ingest) or **attach** (we connect to an inspection
channel the user explicitly designates: DevTools debugging port, ETW session,
process metadata APIs). Attaching is permitted only to channels that exist to
be inspected, never to application endpoints, and never carrying reconstructed
application payloads. The single socket-touching module (`apire/capture/`)
is the audited surface; everything else in the engine is statically incapable
of I/O. See ADR-003.

## Response envelope (remcp contract)

```json
{"ok": true, "target": "<session|capture|export>", "method": "<action>",
 "reliability": "sound", "warnings": [{"code": "...", "detail": "...", "impact": "degraded"}],
 "result": { ... }}
```

Errors are in-band JSON payloads (`ok: false`, `error: {code, message, ...}`),
never protocol errors. Responses clip at `APIRE_MAX_RESPONSE_CHARS` (default
120,000) with an in-band `response_clipped` warning that names the narrowing
query. Empty captures, lost salts, rejected proposals, and dropped frames are
warnings with stated impact, never silent.

## Limits and failure behavior

- `APIRE_MAX_CAPTURE_BYTES` (default 512 MB per capture) — enforced at
  ingestion, warning + graceful stop, never a truncated silent store.
- Store corruption: unreadable KB JSON raises `StoreError`; frame blobs are
  content-addressed, so a corrupt blob is detected by hash and reported as a
  warning with the affected capture IDs.
- The engine refuses to start a capture without an authorization statement
  (see security-model).
