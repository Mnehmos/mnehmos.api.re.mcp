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
- SHA-256: see `installers/SHA256SUMS.txt` (pinned at download time; verify
  before any reinstall)
- Trial = full version; licensing does not affect observation.
- Installed at `F:\FL Studio\` (silent NSIS install, 2026-09-12).

## What has been observed so far (2026-09-12, first session)

Capture IDs are machine-local (store: `apire_kb/`, gitignored).

| Finding | Evidence |
| ------- | -------- |
| `FL64.exe` is the main process (PID 44492 this run) | capture `cap_639ad53b1d8c` (process_meta/v2), claim `clm_ef1010918399910d` @ INFERRED |
| FL Studio 26 embeds a Chromium UI: `msedgewebview2.exe` runs as a child of FL64.exe | capture `cap_639ad53b1d8c`; child link verified via psutil during recon (not itself a stored claim); claim `clm_4ec8f2f3600ff743` @ INFERRED |
| FL64.exe loads ~149 modules in this install | capture `cap_639ad53b1d8c` (module_scan + module_loaded frames) |
| FL64.exe makes outbound TLS to CDN infrastructure (Cloudflare/Google edges) at startup | capture `cap_639ad53b1d8c` (connection frames); connections are transient — the detailed snapshot caught 88 established system-wide |
| OSC server is **off** by default: no UDP sockets on FL64; no config in the registry keys (`HKCU\Software\Image-Line\FL Studio 26`, `\Shared`) reveals OSC settings; remote-scripts folder is empty | direct psutil recon + registry query, 2026-09-12 |

### Instrument lesson (encoded as a guard)

The first two "FL absent" captures were taken with process_meta/**v1**
(summary frames only); the FL-present detailed capture used **v2**
(per-entity frames). Correlating across them showed *every* process as
"exclusive to FL present" — including `svchost.exe`. That is an instrument
confound, not evidence. The correlator now detects it: `api_re_observations
correlate` returned `reliability=unreliable` with
`instrument_version_mismatch` (`['process_meta/v2', 'unknown']`) and refused
to present the candidates as trustworthy. **Rule: re-take the baseline with
the current instrument before believing exclusivity.**

## Next session recipes (human-in-the-loop)

1. **Baseline re-take (5 min, required before any further diffing):**
   close FL Studio; capture `process_meta` v2 with label `FL absent` ×2;
   launch FL Studio; capture v2 with label `FL present` ×2; then
   `api_re_observations correlate`. Expected candidates: `FL64.exe`,
   `msedgewebview2.exe`, FL modules, FL64 connections — and *not*
   `svchost.exe`.
2. **H1 — OSC:** in FL Studio, enable the OSC server (Options → MIDI
   settings → OSC; set an output port), then observe with
   `api_re_capture action=start transport=udp_observe port=<that port>` while
   performing labeled UI actions (select channel / rename ×2 with different
   lengths / open plugin browser). The listener is passive: FL sends, we
   listen.
3. **H5 — WebView2 DevTools attach (new):** relaunch FL Studio with
   `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9222`
   set in the environment; this exposes FL's embedded browser to
   **passive attach** (the `devtools_attach` transport, M6). This makes the
   WebView's HTTP/WS traffic — the modern FL UI surface — observable without
   touching FL's own protocol. The env var enables an inspection channel the
   user designates; apire still never sends application requests.
4. **H3 — bridges:** load a VST plugin (bridged) and capture `process_meta`
   with hint on the bridge process; plugin-host IPC hypotheses can then be
   checked against observation, not belief.

## Campaign protocol (unchanged)

1. Inventory session (done once; repeat per FL version).
2. Hypothesis sessions (H1–H5), each an issue, hypothesis stated *before*
   capture.
3. Differential batteries: labeled human-performed actions.
4. Interpretation valve: proposals at zero confidence; evidence decides.
5. Audit: a fresh session attacks every STRONGLY_INFERRED+ claim with
   `api_re_evidence explain` and `contradictions` before publication.

## Deliverable

An `api_re_export mcp_candidate` capability surface for FL Studio — the
"FL Studio MCP" arm of the capability foundry — plus the honest measure:
how much of the surface remains UNKNOWN, stated plainly.

## Rules

- The tool never sends anything to FL Studio. The human clicks; the tool
  watches. (Relaunching FL with an env var that enables an inspection
  channel is a human decision, recorded in the session hypothesis.)
- OSC/pipes used by *other* software on the machine may appear in captures;
  they are noise until correlated, and correlating them is the correlator's
  job, not a reason to widen capture filters beyond the authorized
  statement.
