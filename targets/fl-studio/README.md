# Challenge target — FL Studio

The opaque target: a native DAW with no usable public API documentation.
Success here is not a score; it is a semantic map whose every claim survives
an independent evidence audit ([docs/evaluation.md](../docs/evaluation.md)).

## Installer (staged, gitignored, machine-local)

- File: `installers/flstudio_win64_26.1.6.5639.exe`
- Version: 26.1.6 build 5639 (Windows, ~1.03 GB)
- Source: official Image-Line redirect
  `https://support.image-line.com/redirect/flstudio_win_installer`
  → `https://install.image-line.com/flstudio/flstudio_win64_26.1.6.5639.exe`
- SHA-256: see `installers/SHA256SUMS.txt` (pinned at download time)
- Installed at `F:\FL Studio\` (silent NSIS install, 2026-09-12).
- Trial = full version; licensing does not affect observation.

## Observation log (session 2, autonomous, 2026-09-12)

Capture IDs and claim IDs are machine-local (store `apire_kb/`, gitignored).

### Differential result (process_meta v2, four labeled captures)

Conditions: `FL absent` ×2 (`cap_6699ab1cabfe`, `cap_68746cdaf15a`) vs
`FL present` ×2 (`cap_1cf3313ce9c3`, `cap_15592f6e78d6`). All captures
same instrument (`process_meta/v2`) → **reliability=sound, no warnings**;
144 candidates, all exclusive to FL-present, none to FL-absent. Examples:

- `process msedgewebview2.exe` (FL's embedded Chromium renderers)
- module loads: `ilwasapi2asio_x64.dll` (Image-Line ASIO driver),
  `dsound.dll`, `mmdevapi.dll`, `msacm32.dll` (the audio stack)
- `socket tcp 127.0.0.1:9222 msedgewebview2.exe` (the debug channel itself)
- No `svchost.exe`-style artifacts: the instrument confound from session 1
  is gone under matched instruments.

### FL's cloud API surface, observed passively (devtools_attach)

Method: FL relaunched with
`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9222`,
apire attached to the page target *before* navigation and observed the full
FL-Cloud grid load. Capture `cap_0144babac9e8`: 153 frames from 897 CDP
events. Claims at INFERRED 0.40 (proposed at 0.0, raised by verified
`captured_traffic` provenance), except where contradicted below:

| Observation | Semantic claim |
| ----------- | -------------- |
| `HEAD /online.txt` ×3 | `flstudio.cloud.connectivity_check` |
| `GET /api/frontend` (host `unleash-edge.cloud.image-line.com`) | `flstudio.cloud.feature_flags` — **rival reading held**: `flstudio.cloud.frontend_config`; both linked as contradictions |
| `POST /api/frontend/client/metrics` (same host, authenticated) | `flstudio.cloud.client_metrics` |
| `POST /api/{var}/envelope/` ×4 | `flstudio.cloud.telemetry_envelope` |
| `GET /content/additional-component-data/` | `flstudio.cloud.content.component_data` |
| `GET /filter/genre` (with `/filter/instrument`, `/label`, `/product/labels/available`, `/product/sales/all-trending-packs/...`) | `flstudio.cloud.catalog.filter_genre` |
| `GET /waveform/<url-encoded CDN URL>` (dozens of per-sound URLs) | `flstudio.cloud.waveform_render` |
| Next.js data routes `/_next/data/<buildId>/fl-studio-*.json` | not yet claimed (build-id segment varies; needs a path-template rule) |
| GA4 `POST /g/collect`, GTM `/gtag/js`, `/tag` | not yet claimed (third-party analytics, out of scope for FL semantics) |

**Authentication evidence:** 4 requests carried an `Authorization` header
(all on the Unleash host) — stored as `<REDACTED>` by the ingestion gate,
as were 33 credential-shaped values and 14 sensitive keys across the
captures. Zero leaks (redaction audit over stored manifests).

### Native-process claims

- `flstudio.main.process` (`FL64.exe`) — INFERRED 0.40
- `flstudio.embedded.webview` (`msedgewebview2.exe` as FL's child) —
  INFERRED 0.40; the child relation was verified via psutil during recon
  but is not itself a stored claim yet.

## M6 session: response bodies, settled contradiction, audit (2026-09-12)

Capture `cap_5350bc449977` (`devtools_attach/v2`, bodies enabled): 155
frames, 970 CDP events, **51 response bodies captured** (25 without: 14 over
the 2 MB fetch cap — the biggest Next.js data files — and 11 pending at
stop). Two bugs were found and fixed by making this work: a stashed-frame
double-pop that silently dropped every fetched body, and — caught by the new
SSE test — a streaming relay that bypassed the reader buffer and skipped
early events.

### The Unleash-vs-config rivalry is settled by evidence

The captured body of `GET /api/frontend` is
`{"toggles":[{"name":"sign_in_flow","enabled":true,"variant":{...},
"impression_data":true}, ...]}` — the Unleash client API format. Disposition:

| Reading | Level | Support |
| ------- | ----- | ------- |
| `flstudio.cloud.feature_flags` | **STRONGLY_INFERRED 0.70** | response body shape (`toggles` array), verified `captured_traffic` + `schema_induction` on the response observation |
| `flstudio.cloud.frontend_config` | INFERRED 0.40 | earlier URL-shape reading only |

Both remain in the graph, linked as contradictions — the rival is settled by
evidence, not deleted by decree. `api_re_evidence explain` shows the
asymmetry.

### Other findings from bodies

- **`flstudio.telemetry.sentry` (STRONGLY_INFERRED 0.60)**: the envelope
  endpoint resolves to `o1373866.ingest.sentry.io` with `sentry_version=7`
  and a redacted `sentry_key` — Sentry envelope ingestion (project 6685788),
  a third party under Image-Line's account, not an IL service. Linked to the
  older `telemetry_envelope` reading as rivals.
- **`flstudio.cloud.catalog.filter_genre` raised to STRONGLY_INFERRED 0.70**
  (5007-byte genre-list body; `@body` array representation inducts the item
  signature).
- Endpoints returning catalog arrays (genre/instrument/labels) now carry
  `@body` array shapes with item signatures; the exporters emit real array
  schemas from them.

### Audit pass (exercised on real data)

- **12 claims** at INFERRED+; three at STRONGLY_INFERRED (above).
- **64 UNKNOWN observations** — the honest measure; led by
  `HTTP 200 /waveform/{var}` (44 sightings, unclaimed response side),
  `OPTIONS /api/frontend` preflights (9), `/online.txt` responses (9),
  `/g/collect` 204s (8), and the `/_next/data/...` JSON routes. Stated
  plainly: the reconstruction knows what those endpoints *are* far less than
  where they can be reached.
- **One stranded claim flagged**: `clm_1fecad51f822e83f` (the earlier
  waveform reading) had its subject re-keyed by this session's exact-status
  change; `explain` now reports `subject_resolves: false` with a re-anchor
  note instead of pretending. (The re-anchor procedure itself was
  demonstrated earlier with `clm_6e84cd6c81910b27`.)
- **Zero secrets** in the new capture: Sentry's `sentry_key` was redacted at
  ingestion (`<REDACTED>`), verified on the stored manifest.

### Known limitations (stated, not hidden)

- **Multi-host path collisions**: canonical keys for HTTP do not include the
  host, so `GET /tag` on `search.cloud.image-line.com` and
  `www.googletagmanager.com` merge into one observation. Evidence:
  `obs_bf6918062788c2b6` shows one `GET /tag`. Fixing requires keying v2 and
  re-anchoring existing claims — see ADR-009 for the plan and trigger.
- 14 responses exceed the 2 MB body-fetch cap (the largest Next.js catalog
  JSONs); their headers are captured, bodies are not. Raising the cap is a
  one-line change when a schema question needs those files.

## Next observations (no human needed)

1. **OSC — falsified (2026-09-12).** FL Studio 26.1.6 has no OSC support at
   all: all ten Settings tabs checked, zero protocol-OSC strings in the
   engine's UI vocabulary, a 25-minute passive listen on 127.0.0.1:9000
   recorded nothing during active UI use, and no UDP sockets were ever
   observed on FL64. Evidence: `evidence/h1-osc-falsified/`.
2. **Plugin bridges (H3):** per ADR-008, capture `process_meta` with a hint
   matching the bridge process and inspect `named_pipes`/`pipe_present`
   evidence for structure (names, versions) — messages are not observable.
3. **Raise preflight noise out of the unknowns**: OPTIONS observations are
   CORS mechanics, not API surface; a normalizer rule could classify them
   (deliberate change, re-anchor discipline applies).
4. **Ecological control tier** (open5e-api/Gitea) for the benchmark's
   messier second tier.

## Campaign protocol (unchanged)

1. Inventory session (repeat per FL version).
2. Hypothesis sessions (H1–H5), each an issue, hypothesis stated *before*
   capture.
3. Differential batteries: labeled human-performed actions.
4. Interpretation valve: proposals at zero confidence; evidence decides;
   rival readings are kept as linked contradictions.
5. Audit: a fresh session attacks every STRONGLY_INFERRED+ claim with
   `api_re_evidence explain` and `contradictions` before publication.

## Deliverable

An `api_re_export mcp_candidate` capability surface for FL Studio — the
"FL Studio MCP" arm of the capability foundry — plus the honest measure:
how much of the surface remains UNKNOWN, stated plainly.

## Rules

- The tool never sends anything to FL Studio. The human (or the operator's
  agent) clicks; the tool watches. Enabling a debug channel at launch is an
  operator decision, recorded in the capture's authorization statement.
- OSC/pipes used by *other* software on the machine may appear in captures;
  they are noise until correlated, and correlating them is the correlator's
  job, not a reason to widen capture filters beyond the authorized
  statement.
