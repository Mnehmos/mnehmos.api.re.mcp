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
| `review` | `claim_id` | the claim's current standing: which evidence raised/lowered it, what would confirm or refute |
| `link` | `claim_id`, `related_claim_ids` (default []) | proposed relationships between claims (stored as proposals; relations earn confidence the same way) |

### `api_re_export` — specifications out

| Action | Emits |
| ------ | ----- |
| `openapi` | OpenAPI 3.1 document from HTTP observations + induced schemas |
| `asyncapi` | AsyncAPI document from WS/SSE/pipe event observations |
| `json_schema` | induced payload schemas |
| `protocol_spec` | protocol catalog: transports, message types, ordering rules, error semantics |
| `architecture` | architecture map: processes, connections, services, boundaries |
| `mcp_candidate` | proposed semantic capability surface: `project.get`, `track.plugins`, `project.events`… derived from the graph — a *specification of* an MCP, not an implementation of calls. The normal RE workflow decides which surfaces deserve to exist. |

Every export element carries `evidence_level` + `confidence` + citing
captures; elements below the `min_level` parameter (default `INFERRED`) go to
a separate `speculative` section. Authentication is always exported as
"existing application session; credential material REDACTED at ingestion".

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
