# Changelog

## 0.5.1 — 2026-09-12

Ecological benchmark tier + the two engine defects its first run exposed.

### Added

- `targets/control/ecological/`: Gitea 1.27.3 as the ecological control —
  a real application with its own published spec. Committed recipe
  (`run_gitea.cmd`, relative-path `app.ini`), scorer
  (`score_ecological.py`), README with first results. Not in CI (needs the
  binary); run manually when touching transports or redaction.

### Fixed (found by the ecological tier on its first run)

- **The proxy sent no `Host` header upstream.** Python's http.server never
  noticed; Gitea's Go server answered every proxied request with 400. The
  proxy now rebuilds `Host` from the absolute-form target. Regression test
  added.
- **Credentials inside JSON-*string* bodies were not redacted.** A signin
  POST captured as `postData` text bypassed key-name rules and the fixture
  password reached the manifest. The redactor now parses JSON strings and
  applies key-name rules recursively (log lines and HAR body samples had
  the same hole). Regression test added.

### Ecological first results

- Endpoint precision 0.500: two honest misses — a word-like path segment
  (`/users/apire-does-not-exist`) is not collapsed (genuine single-sighting
  ambiguity; the two-sighting rule is a recorded normalizer v3 candidate),
  and one probed route that Gitea itself 404s.
- Version schema agreement 1.000 (spec resolved through its two-hop `$ref`
  indirection); secrets 0.

## 0.5.0 — 2026-09-12

Every advertised action answers; ADR-009 implemented; body-fetch cap raised.

### Added (commit 8f5eccd)

- `protocol.events` (SSE + WS lifecycle, split from data `messages`),
  `protocol.schemas` (induced shapes with evidence), `protocol.errors`
  (4xx/5xx plus refused CONNECTs).
- `architecture.services` (hosts clustered by registrable domain — IPs stay
  whole — with their observed local client processes),
  `architecture.boundaries` (loopback / local network / public internet
  with the processes crossing them).
- `evidence.experiments` (apire/experiments.py): deterministic proposals of
  observations the OPERATOR could perform to raise a claim or settle a
  contradiction, each citing the claim/observation that generated it.
  The tool never pokes the target; this is what the operator does next.

### Changed

- **ADR-009 implemented**: HTTP canonical keys include the host; the KB
  header records `normalizer_version`, and a mismatch surfaces as a warning
  on every read tool. `scripts/reanchor_v2.py` migrated the live KB: 9
  claims re-anchored, 1 historically stranded claim skipped (still flagged),
  0 failed. The migration is what ADR-009 promised, now proven on real data.
- **Store fails closed against concurrent sessions**: if the KB file
  changed on disk since this session loaded it, saves raise `StoreError`
  with recovery instructions. This is not theoretical — a long-lived
  background session silently clobbered the first migration with its stale
  in-memory copy. Two live sessions can no longer lose writes.
- Body-fetch cap raised 2 MB → 8 MB, `APIRE_MAX_BODY_FETCH` to override (the
  largest Next.js catalog files were being skipped; they are the schema
  source).
- `project.messages` labels WS frames by connection URL.
- `kb.save_claim` now updates the subject on re-save by claim id — the
  re-anchor test caught that it silently kept the old one.

### Fixed

- The wire test no longer writes into the real evidence KB (it proposes
  claims on every run; `APIRE_KB` is set to a temp dir). 13 junk claims
  from earlier test runs were pruned from the local KB.

## 0.4.1 — 2026-09-12

Operator tooling + hypothesis H1 falsified.

### Added

- `targets/fl-studio/operator_gui.py` — the human role, automated
  (activate/click/type/screenshot; one process per act-and-observe cycle,
  because window focus is stolen back within a second otherwise). Not part
  of the engine; requires pyautogui, which is deliberately not a server
  dependency.
- `targets/fl-studio/ocr.ps1` — perception without a vision model: the
  built-in Windows OCR engine, printing text with pixel bounding boxes so
  coordinates can be clicked. Line mode and word mode.

### Findings

- **H1 falsified: FL Studio 26.1.6 has no OSC support.** Evidence (four
  independent lines, recorded in
  `targets/fl-studio/evidence/h1-osc-falsified/`): all ten Settings tabs
  checked (MIDI, Audio, General, File, Theme, Project, Info, Debug,
  Account, About) — no OSC anywhere; zero protocol-OSC strings in the
  engine's UI vocabulary (only oscillator labels); a 25-minute passive
  listen on 127.0.0.1:9000 (`cap_a1c3b532188b`) recorded 0 frames during
  active UI use; no UDP sockets ever observed on FL64.
- The computer-use plugin's host requires ZCode's permission-broker
  socket; rather than speak that private protocol, the operator tooling
  above was used — same authority, no boundary bypassed.

## 0.4.0 — 2026-09-12

M6 complete (OSC excepted, human-gated). 74 tests + 17-check wire test.

### Added

- `devtools_attach` v2: opt-in, size-capped response bodies via
  `Network.getResponseBody` (in-flight command tracking; frames are stashed
  at `responseReceived` and completed when the body arrives; stop-flush
  reports anything incomplete), and WebSocket lifecycle events
  (open/closed/handshake) keyed per connection.
- `http_proxy`: streaming SSE relay — event-stream responses are relayed
  incrementally (never waited to EOF, which would break the observed app)
  and each complete event becomes an `sse_event` frame.
- Normalizer: responses key by **exact status** (204 vs 200-with-body are
  different behaviors); response bodies induct from decoded JSON, with an
  `@body` metadata representation for array bodies (item signature +
  observed lengths) that the exporters turn into real array schemas.
- `api_re_evidence` gained a `limit` (default 20) after the unknowns listing
  exceeded context on real data.
- `api_re_evidence explain` now reports `subject_resolves`: a claim whose
  observation was re-keyed by a normalizer change is visibly stranded with a
  re-anchor note instead of pretending.
- ADR-009: host belongs in HTTP canonical keys — deferred with a plan,
  evidence (`GET /tag` merged across two hosts), and the re-anchor
  procedure recorded.

### Fixed (all found by dogfooding)

- Body fetch silently dropped every fetched frame (stash popped twice; the
  reply handler looked in a map the loadingFinished branch had emptied).
- SSE relay skipped early events by reading the raw socket while the header
  parse had already buffered them — the same buffer discipline `_Reader`
  exists for, violated in a new place; its test now pins it.
- SSE event splitting assumed LF line endings; wire format is CRLF.

### FL Studio

- The Unleash-vs-frontend_config rivalry is settled by captured evidence:
  `/api/frontend` returns `{"toggles":[...]}`, so `flstudio.cloud.feature_flags`
  rises to STRONGLY_INFERRED 0.70; the rival stays linked at INFERRED 0.40.
- The envelope endpoint is Sentry (`o1373866.ingest.sentry.io`), captured
  with its key redacted: `flstudio.telemetry.sentry` @ STRONGLY_INFERRED.
- Audit published in targets/fl-studio/README.md: 12 claims, 64 unknowns,
  stranded claims flagged, zero secrets.

## 0.3.0 — 2026-09-12

M2 complete: loopback proxy + control benchmark. 69 tests + 17-check wire test.

### Added

- `http_proxy` transport: loopback passthrough proxy. Forwards exactly what
  the client sent, relays the origin's response, records both sides with
  truncated body samples. CONNECT is refused (501, recorded) — an opaque
  tunnel is unobservable. Body-aware schema induction: HTTP responses now
  induct from decoded JSON bodies (the API), not the transport shell;
  response-body definitions and OpenAPI response schemas follow.
- Control benchmark: `targets/control/reference_app/` (stdlib reference app
  + committed OpenAPI spec with a planted `created_at`/`created_ts`
  discrepancy) and `targets/control/score.py`, run in CI via
  `tests/test_benchmark.py`. First results: endpoints 1.000/1.000,
  schema property P/R 0.75/0.75 (the gap *is* the planted discrepancy),
  discrepancy flagged, zero secrets.
- `_Reader`: buffered socket reader for the proxy — head reads must never
  swallow body bytes (a live defect the proxy tests caught in the first
  implementation).

### Fixed

- The no-egress scanner was over-broad: it banned the `urllib` root, so
  even `urllib.parse` (pure parsing) tripped it while `from urllib import
  request` would have slipped through the root check. Now module-path
  precise (`urllib.parse` allowed; `urllib.request`, `from urllib import
  request`, `from http import client` flagged) with a dedicated precision
  test. A scanner nobody is tempted to weaken.

## 0.2.0 — 2026-09-12

M5 complete: the six specification exporters. 61 tests + 17-check wire test.

### Added

- `apire/export/`: `openapi` (3.1), `asyncapi` (2.6), `json_schema`,
  `protocol_spec`, `architecture`, `mcp_candidate`. Every element carries an
  `x-apire` evidence block; anything below `min_level` moves to a
  `speculative` section. `api_re_export` writes to `path` (directory gets
  `<action>.json`) or returns the document inline.
- Honesty surfaces in the documents: `unmatched_responses` (responses whose
  request was never captured), explicit authentication posture, and a
  guarantee line on `mcp_candidate` stating it specifies capabilities and
  implements none.
- Normalizer: opaque path segments (base64 blobs, URL-encoded CDN URLs,
  Next.js build ids) collapse to `{var}` — per-sound waveform URLs are now
  one observation with 22 sightings instead of dozens of n=1 rows, and
  `/_next/data/<buildId>/…` routes group. Closes the roadmap's noted gap.
- Dogfood client: `@file` script support (shell quoting is never part of an
  observation session).
- Committed specimen: `targets/fl-studio/exports/mcp_candidate.json`.

### Changed

- Claims whose observations were re-keyed by the normalizer change are
  re-anchored by re-proposing against the new observation (the waveform
  claim: `clm_6e84cd6c81910b27` @ INFERRED, 22 sightings). Lesson recorded:
  observation ids derive from canonical keys, so normalizer changes are
  deliberate acts — deferred: versioned normalization with claim re-derivation.

## 0.1.1 — 2026-09-12

Autonomous FL Studio campaign: differential proof, WebView2 attach transport,
first observation of FL's cloud API surface. 51 tests + 15-check wire test.

### Added

- `devtools_attach` transport: attaches to a designated DevTools channel
  (WebView2 `--remote-debugging-port` at launch) and observes HTTP/WS
  traffic passively. Sends only `Network.enable` (a debugger control
  command); never drives the page. WS frames are stamped with their
  connection URL and key per-connection in the normalizer.
- Hand-rolled HTTP/1.1 client for `/json/list` (urllib.request is on the
  engine ban list; the ban was not weakened for convenience).
- `tests/test_devtools.py`: event-mapping tests, raw HTTP client test
  against a local socket server, and a live attach test that skips when no
  debug port exists.
- No-egress scan now confines `websocket`/`socket`/`ssl`/`selectors` to
  `apire/capture/`.
- Dogfood client: `$LAST_CAPTURE` / `$LAST_CLAIM` chaining for multi-step
  sessions in one server process.

### Fixed (all found by live dogfooding, not review)

- Raw HTTP reader hung on Chromium's keep-alive `/json/list` (read-to-EOF);
  now honors Content-Length and chunked encoding.
- CDP WebSocket handshake rejected (403) when an Origin header is sent;
  client now suppresses it.
- Attached-but-closed DevTools channels were silent; the listener records
  the closure as a capture warning.
- `http_response` observations had no endpoint label (useless grouping);
  now `HTTP <status> <path-template>`.

### FL Studio findings (evidence in targets/fl-studio/README.md)

- Differential proof under matched instruments: 144 FL-exclusive candidates
  (reliability=sound), no cross-capture confounds.
- FL 26's UI is an embedded Chromium (WebView2) loading
  `sounds.cloud.image-line.com/fl-studio-grid`; its cloud API observed:
  Unleash feature-flag evaluation (`unleash-edge.cloud.image-line.com`),
  catalog filters, per-sound waveform rendering, telemetry envelope,
  connectivity probe. 10 semantic claims at INFERRED with verified
  provenance; one pair of rival readings kept as linked contradictions.
- Redaction gate exercised on live traffic: 4 Authorization headers + 33
  credential-shaped values + 14 sensitive keys, all stored redacted.

## 0.1.0 — 2026-09-12

First working engine + server, dogfooded on live FL Studio. 44 tests +
15-check stdio wire test, all green.

### Engine (`apire/`)

- `redaction.py` — ingestion gate: header denylist, credential shapes, URL
  query values, embedded tokens in log lines; pseudonymize mode with salt
  fingerprint. Store-bytes assertion tests (no token reaches the manifest).
- `store.py` — append-only capture manifests (batch fsync), atomic KB with
  `.bak`, salt-change detection, authorization-statement gate, label/note
  anchoring. Rejects frames appending to ended captures.
- `normalize.py` — canonical keys per observable behavior; per-entity keys
  for process/module/socket/connection events (stable identity, not pids);
  shape induction (constants, enums, variable fields).
- `correlate.py` — differential correlation: exclusivity by condition label,
  temporal support, periodicity classification (heartbeat noise), candidate
  signals; **instrument-version mismatch guard** (confounded comparisons are
  reported unreliable, not presented as evidence).
- `kb.py` — closed provenance vocabulary with caps and deterministic
  verifiers that recompute from the store and reject unverifiable writes;
  `llm_proposal` cap pinned at 0.00; corroboration rule (>0.40 needs ≥2
  classes); contradictions linked, not hidden; unknowns ranked.
- `semantics.py` — the intake valve: proposals stored verbatim at zero
  confidence; evidence attach raises them only through policy verification.
- `capture/` — `file_ingest` (HAR/log), `udp_observe` (OSC decoder), and
  `process_meta` (psutil snapshot, v2 per-entity granularity) transports.
  Sockets only touch I/O here; listeners never originate requests.

### Server (`server.py`)

- Seven action-enum tools exactly as specified; `@tool` exception boundary;
  in-band envelope warnings; response clipping.
- Tool-surface test pins the surface: seven tools, no transmission verbs,
  no `Optional` params, every handler wrapped.

### Dogfooding on FL Studio (26.1.6, installed to `F:\FL Studio`)

- First real evidence: 883-frame snapshot — FL64.exe (2 sightings), 149
  modules, 88 established connections, WebView2 child process.
- Semantic valve exercised on real observations: `flstudio.main.process`
  and `flstudio.embedded.webview` proposed at 0.0, raised to INFERRED 0.40
  with verified `captured_traffic` provenance.
- Instrument confound found and fixed: mixed-version captures produced
  fake exclusivity; the correlator now flags it (`reliability=unreliable`).

## 0.0.1 — 2026-09-12

Planning and safety infrastructure (M0). No engine code yet.

- Governing rule committed: **Observe applications. Never impersonate them.**
- Design docs: architecture, security model, evidence model, tool surface,
  roadmap, dual-target evaluation benchmark.
- ADRs 000–007: model role, weights/specification/verdict split, passive-only
  by construction, redaction at ingestion, action-enum surface, dual-target
  benchmark, storage layout.
- Canonical schemas (JSON Schema drafts): capture, frame, observation,
  evidence link, semantic proposal, response envelope.
- Safety kit: CI, PR/issue templates, smoke test, no-egress capability scan
  (the verifier that enforces the governing rule), handoff template.
- FL Studio 26.1.6 Windows installer staged for the challenge target
  (gitignored, machine-local).
