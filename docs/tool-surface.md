# Tool surface

Seven tools, each an **action enum over one domain**, per the workspace
action-enum doctrine (`F:/Github/MCP_CONSOLIDATION_PLAN.md`): one tool per
domain a caller works in during one sitting, ≤ 8 actions per tool, strict
per-action union validation behind the advertised enum, optional parameters
with plain defaults (never `Optional[...]` — FastMCP would emit `anyOf`,
which strict providers reject).

The surface is deliberately small because **absence is a guarantee**: there is
no send/replay/execute/modify action anywhere. `tests/test_tool_surface.py`
pins this — the registered schema must contain none of those verbs.

## Tools

### `api_re_capture` — control observation spans

| Action | Params | Returns |
| ------ | ------ | ------- |
| `start` | `transport` (http_proxy \| log_tail \| file_ingest \| devtools_attach \| pipe_listen \| udp_observe \| process_meta), `authorization_statement` (required, non-empty), `name`, `filter` (default "") | session/capture handle, listener status |
| `stop` | `capture_id` | capture summary (frames, bytes, sha256) |
| `status` | `capture_id` (default "" = all) | frame counters, dropped, redaction counts, listener health |
| `list` | `session_id` (default "") | captures with labels, conditions, frame counts |
| `label` | `capture_id`, `label`, `hypothesis` (default "") | updated capture (the experimental condition) |
| `note` | `capture_id`, `note` | appended human annotation (action markers for temporal correlation) |

Refuses `start` without `authorization_statement` (schema-required, not
prompt-enforced).

### `api_re_observations` — the capture store, queried

| Action | Params | Returns |
| ------ | ------ | ------- |
| `list` | `capture_id`/`kind`/`endpoint_prefix` filters, `limit` (default 50) | observations (deduplicated) |
| `inspect` | `observation_id` | full detail: sightings, capture refs, redaction report, induced shape |
| `compare` | `capture_ids` (2–8), `baseline_id` (default "") | per-`canonical_key` diff: exclusive-to, appeared-in, disappeared-in, count deltas |
| `correlate` | `capture_ids` (≥ 2, labeled) | exclusivity table, temporal relations, periodic noise report, candidate discriminators |

### `api_re_protocol` — the reconstructed protocol

Actions: `transports`, `endpoints`, `messages`, `events`, `schemas`, `errors`.
Read-only projections of the evidence graph; every element carries
`evidence_level`, `confidence`, and citing capture IDs. `messages` accepts
`semantic_name_prefix` to filter by proposed/established names.

### `api_re_architecture` — the deployment map

Actions: `processes`, `connections`, `services`, `boundaries`. Built from
process metadata, socket/pipe topology observed in captures, and bundle
references. This is where "the app talks to a local plugin host over a named
pipe" becomes a stored, evidenced claim rather than a hunch.

### `api_re_evidence` — the honesty surface

| Action | Params | Returns |
| ------ | ------ | ------- |
| `query` | `subject`/`min_level`/`provenance_class` filters | claims with full provenance |
| `explain` | `claim_id` | verification record, recomputation details, citing captures |
| `contradictions` | `subject` (default "") | open counter-evidence per claim |
| `unknowns` | `sort` (frequency \| salience) | uninterpreted observations |
| `experiments` | `subject` (default "") | proposed human-performed discriminating observations, each tied to an open question |
| `policy` | — | the evidence policy: vocabulary, caps, verifiability, thresholds (self-description for calling models, remcp `re_kb_policy` analog) |

### `api_re_semantics` — the LLM intake valve (the only write path for interpretations)

| Action | Params | Returns |
| ------ | ------ | ------- |
| `propose` | `subject`, `proposed_name`, `rationale`, `evidence_refs` (default []) | stored proposal @ confidence 0.0 — accepted shape-wise, granted nothing |
| `attach_evidence` | `claim_id`, `provenance_json` (capture-derived provenance list), `confidence` | the claim re-evaluated: each verifiable class recomputed against the store, rejected on failure |
| `review` | `claim_id` | the claim's current standing: which evidence raised/lowered it, what would confirm or refute |
| `link` | `claim_id`, `related_claim_ids` (default []) | proposed relationships between claims (stored as proposals; relations earn confidence the same way) |

### `api_re_export` — specifications out

All six actions are live. Params: `min_level` (default `INFERRED`) and
`path` (a directory gets `<action>.json`; empty returns the document
inline) and optional `capture_ids`.

| Action | Emits |
| ------ | ----- |
| `openapi` | OpenAPI 3.1 document from HTTP observations + induced schemas; numeric/opaque path segments become numbered parameters (`{p1}`), never guessed names |
| `asyncapi` | AsyncAPI 2.6 document from WS/SSE/OSC/pipe observations; channels are the observed addresses/URLs, direction is what was observed |
| `json_schema` | one JSON Schema definition per canonical key, `$defs`-named by semantic claim where one exists |
| `protocol_spec` | the honest catalog: transports, endpoints, messages, 4xx/5xx errors, unmatched responses (no captured request), authentication posture |
| `architecture` | processes, process surfaces (listening/outbound), connections, hosts |
| `mcp_candidate` | proposed capability surface grouped into candidate tools; same-purpose actions merged across payload shapes. **Specifies capabilities; implements none — the document contains no transport definition and there is no call to make.** |

Every element carries an `x-apire` evidence block (level, confidence, citing
captures, claim id). Elements below `min_level` move to the document's
`speculative` section — never silently mixed in. Exports contain no
credential material by construction (redaction ran at ingestion).

## Response contract

remcp envelope, unchanged: `ok / target / method / reliability /
warnings / result`; typed errors as in-band JSON (`ok: false, error: {code,
message, ...context}`); clipping at `APIRE_MAX_RESPONSE_CHARS` with an
in-band `response_clipped` warning naming the narrowing query; `@tool`
wrapper maps `ApiReError` → error dict, `MemoryError` → `out_of_memory`,
bare `BaseException` → `internal_error` with trimmed traceback — a tool call
never crashes the server, and a failed call is followed by a working one
(probe-tested in the wire test, like remcp's).

## Naming

Engine package `apire/`, server `FastMCP("apire")`, tools `api_re_*`,
env vars `APIRE_*`, store `apire_kb/`. Chosen over `api_re.*` dotted names
because MCP tool names are restricted to `[a-zA-Z0-9_-]` — the user-facing
shorthand `api_re.capture` maps to tool `api_re_capture` + `action="capture"`'s
domain (`api_re_capture` *is* the capture domain).
