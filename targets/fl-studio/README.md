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

## Next observations (no human needed)

1. **Native API surface:** FL's OSC server is off by default (no UDP
   sockets; no registry config; empty remote-scripts folder). Enabling it
   requires in-app GUI steps — deferred until a human wants it; the
   WebView path yielded a real surface without it.
2. **Sharpen the rivals:** `/api/frontend`'s Unleash reading can be
   confirmed/refuted by looking for Unleash SDK-shaped responses (feature
   toggle JSON) in a future capture — needs response bodies, which
   devtools_attach v1 does not fetch (`Network.getResponseBody` is the
   next transport upgrade).
3. **Plugin bridges (H3):** load a bridged VST in FL and capture
   process_meta with a hint matching the bridge process name.
4. **Path templates:** teach the normalizer to collapse Next.js build-id
   segments (`/_next/data/<hash>/`) so those routes group.

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
