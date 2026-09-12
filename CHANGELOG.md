# Changelog

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
