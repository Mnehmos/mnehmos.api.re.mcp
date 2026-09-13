# Roadmap

Milestones are vertical slices: each one ends with a tool a model can actually
drive against a real target, and with the evaluation harness of
[evaluation.md](evaluation.md) run against the control target. Test-first
throughout; the verifier lands before the capability it guards.

## M0 — safety infrastructure (done, this commit)

Governing rule, design docs, ADRs, canonical schemas, CI, smoke +
no-egress tests, handoff template, FL Studio installer staged.
First commit is the safety system, not the feature.

**Gate:** repo knows how to be helped — a fresh agent can read CLAUDE.md +
handoff and continue. `pytest` green.

## M1 — redaction + capture store + file ingest (no sockets yet)

**Status: done 2026-09-12** — plus `udp_observe` and `process_meta` landed
early because the FL Studio campaign needed them.

- `apire/errors.py`, `apire/evidence.py` (remcp contracts, renamed domain).
- `apire/redaction.py` with the spec table from security-model; pseudonym
  mode + salt fingerprint.
- `apire/store.py`: append-only capture manifests + content-addressed frame
  blobs; atomic KB JSON with `.bak`.
- Ingest of existing artifacts first: HAR files, log files, exported bundles.
  This exercises the full normalize→store path with zero socket risk.
- Tests: `test_redaction.py` (feed a bearer token through the public ingest
  path; assert the stored bytes never contain it — red first), store
  atomicity/corruption tests, envelope tests.

**Gate:** HAR of the control target ingests; `pytest` green; secret grep clean.

## M2 — loopback HTTP capture + server

**Status: done 2026-09-12.** The 7-tool server landed with the M1/M2
session; the loopback passthrough proxy landed later the same day
(`apire/capture/http_proxy.py`, 6 tests: relay fidelity both directions,
redaction passthrough, CONNECT refusal, 502 on unreachable origin, chunked
relay). The control benchmark ([evaluation.md](evaluation.md)) runs in CI.

- `apire/capture/http_proxy.py`: listen-only loopback proxy (the app points
  at it; it forwards observed exchanges unmodified — passthrough, not
  origination). HTTP first; HTTPS strategy is an ADR before M4.
- `apire/normalize/http.py` → Observation IR with canonical keys.
- `server.py`: FastMCP, seven action-enum tools, `@tool` wrapper, envelope,
  clipping. `api_re_capture` + `api_re_observations` fully live; the rest
  return typed `UnsupportedError` (refusal over guessing, remcp style).
- `tests/test_tool_surface.py`: registered schemas contain no
  send/replay/execute/modify verbs. `tests/wire_test.py`: stdio JSON-RPC
  subprocess client (remcp's), handshake, failure-path liveness probes.

**Gate:** drive the control target through the proxy, get endpoints out of
`api_re_observations`; first benchmark run vs the committed OpenAPI spec.

## M3 — differential correlator

**Status: done 2026-09-12** — exclusivity, periodicity, candidates, and the
instrument-version mismatch guard (a defect found during the FL Studio
dogfood).

- Capture labels + action notes as experimental conditions.
- `apire/correlate.py`: exclusivity, temporal adjacency, periodicity,
  invariance, field discrimination.
- `api_re_observations correlate/compare` live; `api_re_capture label/note`
  live.
- Tests pin the worked example: a synthetic 3-capture fixture where
  `type: 47` is exclusive to condition C with a follow relation, plus a
  heartbeat that must NOT correlate.

**Gate:** benchmark run with labeled spans; exclusivity recomputation
property test (delete a capture → correlator's claim about it fails closed,
not stale).

## M4 — schema induction + evidence graph + KB

**Status: done 2026-09-12** — shape induction, KB policy with recomputing
verifiers, contradictions, unknowns; semantic-name claims exercised on real
FL Studio observations.

- `apire/schema.py`, `apire/kb.py` (closed provenance vocabulary, caps,
  verifiers that recompute against the store), `apire/graph.py`.
- `api_re_protocol` + `api_re_evidence` live.
- Tests: policy rejection tests in remcp's style (`test_false_string_xref_
  claim_is_rejected` analog: `test_unverifiable_differential_claim_is_rejected`,
  `test_llm_proposal_cannot_exceed_zero_confidence`).

**Gate:** every stored claim recomputes from store (property test:
regenerate the graph from captures alone → identical claims).

## M5 — semantics valve + exporters

**Status: done 2026-09-12.** The valve landed with M3/M4; the six exporters
(openapi, asyncapi, json_schema, protocol_spec, architecture, mcp_candidate)
landed with per-element evidence floors, speculative sections, and a
no-secret audit test. Dogfooded on the FL Studio evidence: the candidate
surface groups 10 claims into named tools with every action carrying its
level and citing observations.

- `apire/semantics.py`, `apire/export/*` including `mcp_candidate`.
- `api_re_semantics` + `api_re_export` live; full surface operational.
- Export tests: emitted OpenAPI parses; no secret material in any export
  (fixture contains tokens; assert exports never contain them).

**Gate:** full loop on the control target; benchmark precision/recall
reported; a second opinion pass reviews the mcp_candidate output.

## M6 — WS/SSE + attach transports; FL Studio campaign

**Status: done 2026-09-12 (OSC excepted, human-gated).** Transports:
`devtools_attach` v2 (response bodies via `Network.getResponseBody`,
size-capped; WS lifecycle events open/closed/handshake), `http_proxy` (with
streaming SSE relay and event extraction), `log_tail`; `pipe_listen` removed
by ADR-008. Campaign: bodies settled the Unleash-vs-config rivalry (evidence
in targets/fl-studio/README.md), three claims at STRONGLY_INFERRED, an audit
pass with 12 claims / 64 unknowns / one stranded claim flagged, and the
honest measure published. Known limits recorded: ADR-009 (host in keys),
2 MB body-fetch cap.

- WS + SSE normalizers; the `devtools_attach` transport (browser targets) and
  `log_tail` landed early; named-pipe interception reframed by ADR-008
  (presence/naming via `process_meta`, no listener).
- FL Studio campaign begins per targets/fl-studio/README.md: install,
  capture OSC/pipe hypotheses, run differential sessions with human-performed
  actions.
- HTTPS-capture ADR implemented if the campaign demands it.

**Gate:** first FL Studio semantic map with auditable evidence; contradictions
and unknowns surfaces doing their job (the honest measure: how much is
UNKNOWN, stated plainly).

## Standing rules across all milestones

- Every milestone ships its verifier before its capability.
- The no-egress ban list grows whenever a new transport introduces a new I/O
  primitive; the scan and the transport land in the same commit.
- After any two feature-heavy milestones, the next one is a
  control-strengthening milestone (schema/validator/test debt) — capability
  must not outpace control.
