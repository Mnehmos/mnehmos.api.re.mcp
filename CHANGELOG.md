# Changelog

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
