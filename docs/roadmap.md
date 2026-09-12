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

- `apire/schema.py`, `apire/kb.py` (closed provenance vocabulary, caps,
  verifiers that recompute against the store), `apire/graph.py`.
- `api_re_protocol` + `api_re_evidence` live.
- Tests: policy rejection tests in remcp's style (`test_false_string_xref_
  claim_is_rejected` analog: `test_unverifiable_differential_claim_is_rejected`,
  `test_llm_proposal_cannot_exceed_zero_confidence`).

**Gate:** every stored claim recomputes from store (property test:
regenerate the graph from captures alone → identical claims).

## M5 — semantics valve + exporters

- `apire/semantics.py`, `apire/export/*` including `mcp_candidate`.
- `api_re_semantics` + `api_re_export` live; full surface operational.
- Export tests: emitted OpenAPI parses; no secret material in any export
  (fixture contains tokens; assert exports never contain them).

**Gate:** full loop on the control target; benchmark precision/recall
reported; a second opinion pass reviews the mcp_candidate output.

## M6 — WS/SSE + attach transports; FL Studio campaign

- WS + SSE normalizers; `devtools_attach` (browser targets), `pipe_listen`,
  `udp_observe`, `process_meta` transports.
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
