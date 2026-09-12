# PROJECT_CONTEXT.md

## Purpose

Reconstruct an authorized application's API surface — HTTP, WebSocket, SSE,
local sockets, named pipes/RPC metadata, logs, JS bundles, process metadata —
from **passive observation only**, and emit specifications with a deterministic
evidence trail: OpenAPI, AsyncAPI, JSON Schema, protocol catalog, architecture
map, and a candidate MCP capability surface.

Sister tool to `mnehmos.reverse-engineer.mcp` (remcp, binary RE). remcp
reverses binaries; apire reverses *behavior*. Together they are the front half
of a "capability foundry": software behavior in, capability-server specs out.

## Users

- Mnehmos, driving the tool through an MCP client (ZCode) to design MCP servers
  for applications that have no usable API documentation (FL Studio first).
- Secondary: anyone auditing what an application on their own machine actually
  does on the network — with the same no-egress guarantee.

## Core workflows

1. **Authorized capture.** User states what they are authorized to inspect
   (`APIRE_AUTHORIZATION_STATEMENT`), starts a capture transport, uses the
   application normally; frames are normalized and redacted into the store.
2. **Differential observation.** User performs labeled actions across capture
   spans ("idle", "open project", "rename object"); the correlator diffs them:
   what appeared only in which span, what follows what, what is heartbeat noise.
3. **Interpretation valve.** The LLM proposes semantic names for opaque
   observations (`type: 47` → `plugin.catalog.updated`); `api_re_semantics`
   accepts the proposal but grants it zero confidence; deterministic evidence
   (differential exclusivity, temporal ordering, payload shape) raises or
   declines it. Contradictions and unknowns are queryable; the tool suggests
   discriminating experiments the *human* can perform next.
4. **Specification export.** Evidence graph → OpenAPI / AsyncAPI / JSON Schema
   / protocol spec / architecture map / candidate MCP surface, each element
   carrying its evidence level and provenance.

## Architecture (summary — full: docs/architecture.md)

- `apire/` — engine package, zero MCP imports, zero egress capability. Redactor
  → capture store → normalizers → differential correlator → schema induction →
  evidence KB (closed provenance vocabulary, caps, deterministic verifiers) →
  exporters.
- `server.py` — the only MCP layer. Seven action-enum tools; `@tool` exception
  wrapper; envelope responses with in-band warnings; response clipping.

## Important commands

| Command | Purpose |
| ------- | ------- |
| `pytest` | full suite |
| `python -m pytest tests/test_no_egress.py -q` | passive-only scan |
| `pip install -r requirements.txt` | pinned deps |
| `python server.py` | stdio MCP server (from M2) |

## Constraints

- Passive by construction (no replay/execution capability anywhere).
- Redact credentials at ingestion, before persistence.
- Evidence policy is law: closed provenance vocabulary, per-class confidence
  caps, verifiable classes must pass recomputable checks or the write fails.
- Evidence stores and installers never leave the machine unredacted/uninvited:
  gitignored, never committed.
- Windows-first host (win32), Python 3.11+, stdio transport.

## Security / privacy boundaries

- Observes only what the user is authorized to inspect; the authorization
  statement is required at capture start and stored with the session.
- Credential material never persists (redaction upstream of disk).
- The engine has no egress libraries; CI fails if one appears
  (`tests/test_no_egress.py`).
- Exports describe authentication as "existing application session"; they never
  rehydrate secret material, not even pseudonyms (pseudonyms are KB-internal).

## Generated files

- `apire_kb/` — evidence KB + capture store (gitignored, machine-local).
- Exports go where the user points `api_re_export` (default `./exports/`,
  gitignored via `captures/`-style rules only if the user aims it inside the
  repo; exports are meant to be shared — they contain no secret material by
  construction).

## Common failure modes (anticipated)

- Capture transport silently receives nothing (wrong interface, proxy not
  pointed at). Mitigation: `api_re_capture status` reports frame counters;
  envelopes warn on empty spans.
- Pseudonymization salt lost → old pseudonyms cannot be correlated with new
  captures. Mitigation: salt lives in `.env`, its *fingerprint* (not value) is
  stored in the KB header and checked.
- Heartbeat noise drowning the diff. Mitigation: periodicity detection before
  correlation; heartbeats become observations with their own evidence, not
  garbage.
- Model asserting a semantic name with unearned confidence. Mitigation: policy
  cap; the proposal endpoint physically cannot store confidence > 0 for
  `llm_proposal`.

## Model role

Runtime capability — an LLM drives the tool loop and proposes interpretations;
deterministic code owns capture, redaction, correlation, induction, verdicts,
and exports. Per-tool cards: docs/decisions/001-model-role-card.md. Filled the
ARCHITECTURE_CARD for each runtime capability before that capability lands (see
roadmap milestones).

## Open questions

- Repo location: STANDARDS.md groups MCP servers under `F:\Github\mcp\`, but
  the sibling repos (`mnehmos.reverse-engineer.mcp`, `mnehmos.ooda.mcp`, …)
  still live at the root. Created at root beside its siblings; move together
  with the path-update checklist when the workspace reorg continues.
- HTTPS capture for the control target: loopback plain HTTP first; HTTPS via a
  user-trusted local CA or DevTools-protocol attach is a later milestone
  (ADR needed before M4).
- FL Studio transport hypotheses (OSC? MIDI-scripting host? plugin bridge
  pipes?) are guesses until the first capture says otherwise — see
  targets/fl-studio/README.md.
