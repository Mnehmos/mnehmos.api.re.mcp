# Security model

**Governing rule: Observe applications. Never impersonate them.**

This document states the guarantee in enforcement terms. Adjectives are not
controls; each property below names the mechanism that holds it and the test
that fails when the mechanism breaks.

## What the tool must never be able to do

1. Originate a request to an application endpoint (no replay, no execution, no
   "try this variant").
2. Transmit observed credential material anywhere.
3. Persist credential material.
4. Mutate the observed application (there is no actuator; there is nothing to
   mutate *with*).
5. Silently store, export, or transmit secrets it happened to capture.

## Controls by tier (hierarchy of controls)

### Elimination (the capability does not exist)

- The tool surface has **no replay-shaped action**. `api_re_capture`,
  `api_re_observations`, `api_re_protocol`, `api_re_architecture`,
  `api_re_evidence`, `api_re_semantics`, `api_re_export` — none has an action
  that sends anything. A generated specification *describes* observed traffic;
  describing is not a transport. `tests/test_tool_surface.py` (M2) asserts the
  registered tool schemas contain no send/replay/execute/modify action verbs,
  so a future "helpful" action fails CI.
- The engine has **no egress code**. Banned in `apire/` (non-test code):
  imports of `requests`, `httpx`, `urllib.request`, `http.client`, `aiohttp`,
  `socket.create_connection`/`socket.connect`, `subprocess` with network
  binaries, and any call to `.send(` outside the single sanctioned passthrough
  module. Enforced by `tests/test_no_egress.py` (AST scan) — **this test is
  the governing rule in executable form. Do not weaken it; extend the ban list
  instead.**

### Engineering (capability is boxed where it must exist)

- **Passive capture needs sockets** (a proxy must accept connections and
  respond to the app for the app to keep working). All socket code lives in
  `apire/capture/` under the connect policy of ADR-003: listeners accept;
  attach-mode connects only to user-designated inspection channels (DevTools
  port, ETW). No module outside `apire/capture/` imports socket machinery —
  the no-egress scan enforces the boundary, not just the ban list.
- **Redaction at ingestion, before persistence.** `apire/redaction.py` runs on
  every frame before the store write. The store physically holds
  `Authorization: <REDACTED>` or a pseudonym, never the value. Anything that
  bypasses the redactor to reach the store is a defect even if tests elsewhere
  pass (`tests/test_redaction.py` red-tains this in M1: feed it a frame with a
  bearer token through the public ingest path; assert the stored bytes never
  contain the token).

#### Redaction specification

| Class | Examples | Treatment |
| ----- | -------- | --------- |
| Header denylist | `authorization`, `proxy-authorization`, `cookie`, `set-cookie`, `x-api-key`, `x-auth-*`, `x-csrf-*` | value → `<REDACTED>` |
| Credential-shaped values | `Bearer …`, JWT (`eyJ…` with two dots), AWS `AKIA…`, `gh[pousr]_…`, `sk-…`, long hex (≥ 32), base64 blobs (≥ 40) in auth context | value → `<REDACTED>` |
| Pseudonymizable (equality matters for correlation) | session IDs, device IDs, api-key-shaped strings | HMAC-SHA256(salt, value)[:16] → `~:ab12cd34…` |
| Query/body keys | `token`, `key`, `secret`, `password`, `credential`, `session`, `sig`, `nonce` | key kept, value → `<REDACTED>` / pseudonym |
| URL userinfo, set-cookie body, bearer inside JSON strings | — | same rules applied recursively |

- Mode: pseudonymize when `APIRE_REDACTION_SALT` is set (correlation across
  captures survives; the value does not), full REDACT otherwise.
- The salt never enters the KB; the KB header stores `sha256(salt)[:16]` as a
  *fingerprint* so a salt change is detectable and loudly warned.
- Redaction is itself evidence: each redacted frame records a redaction report
  (which classes fired, counts, no values) so `api_re_observations inspect`
  can show what was removed and why a header reads `<REDACTED>`.
- Known blind spot, stated honestly: values we fail to *recognize* as
  credentials inside opaque blobs may persist. Mitigations: redaction report
  surfaces unrecognized high-entropy blobs for `api_re_evidence unknowns`; the
  authorization statement reminds the human what the store may contain;
  stores are machine-local and gitignored.

### Specification (shape is permission)

- Action enums are the entire action vocabulary; dispatch validates the strict
  per-action union, so an unknown action never reaches the engine.
- Capture start requires `authorization_statement` (non-empty; the human's
  own words about what they are authorized to inspect). It is stored with the
  session and echoed in every export header. The tool cannot start observing
  without it — not as policy theater, but as a schema-required parameter.
- Every export element carries its evidence level; speculative content cannot
  silently pose as observed fact.

### Administrative / procedural

- New remotes default to PRIVATE (STANDARDS.md). Evidence stores and
  installers are gitignored by default and never committed.
- The README says who the tool is for: people inspecting software they are
  authorized to inspect. The tool records that authorization claim; enforcing
  it beyond that is the human's responsibility, and this document says so.

### Detection (when controls leak, you can see it)

- Every stored claim carries recomputable provenance; `api_re_evidence
  explain <claim>` shows the captures and checks behind it.
- `api_re_evidence contradictions` surfaces evidence that argues against
  stored claims — a claim with live contradictions is marked degraded in
  envelopes that include it.
- Secret scan in CI (STANDARDS.md grep) runs on every push.

## Threat model (abridged)

| Threat | Control that stops it |
| ------ | --------------------- |
| Model invents a "helpful" replay action | tool-surface CI test + action-enum dispatch |
| Dependency sprouts an HTTP client that engine code reaches for | no-egress AST scan on every build |
| Captured token tempting in a fixture/test | redaction upstream of persistence + secret scan + fixtures-are-synthetic rule |
| Export rehydrates a secret | exporters project only redacted/derived data; pseudonyms are KB-internal by construction |
| LLM asserts unearned interpretation | `llm_proposal` cap 0.0; confidence comes only from recomputable evidence |
| Store leaks via git | gitignore + STANDARDS secret grep + stores contain no credential material even in the worst case |

## What "read-only" does *not* mean (honesty section)

- Attach-mode inspection channels are read-*oriented* but the OS does not
  guarantee zero side effects (an ETW session costs a little; a DevTools
  connection is visible to the app's debugger hooks). The guarantee is: no
  *application-semantic* mutation, no transmission of captured data, no
  credential persistence — by construction, not by promise.
- A passthrough proxy responds to the application (it must, or the application
  breaks). Those responses replay *the application's own observed exchange*,
  which is what makes the transport passive rather than active; the proxy never
  originates content it did not observe.
