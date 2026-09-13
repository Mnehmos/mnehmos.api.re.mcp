# H1 falsified — FL Studio 26.1.6 has no OSC support

**Date:** 2026-09-12 · **Target:** FL Studio 26.1.6 build 5639 (Windows)
**Hypothesis (H1):** FL Studio's built-in OSC server emits observable UDP
traffic that correlates with UI actions.

**Verdict: falsified.** No OSC surface exists in this version. Four
independent lines of evidence:

1. **Settings GUI, every tab.** The Settings window (Options → MIDI
   settings, or via Options menu) has exactly ten tabs — MIDI, Audio,
   General, File, Theme, Project, Info, Debug, Account, About — and none
   contains an OSC option. The MIDI tab shows only input/output device
   lists, master-sync options and offset; General is display/scaling/
   animation/language; Project is data-folder/save behaviour. OCR text of
   the dialog tabs is in this directory (`ocr-settings-*.txt`).
2. **Engine string table.** The comprehensive UI vocabulary in
   `FLEngine_x64.dll` contains "OSC 1", "AM OSC 3" (oscillator labels) and
   **zero** protocol-OSC strings (no "OSC port", "Send OSC", "OSC Input").
   A feature reachable from the GUI would have its labels there.
3. **Passive listen.** A 25-minute `udp_observe` capture on
   `127.0.0.1:9000` (capture `cap_a1c3b532188b`) recorded **0 frames** while
   FL was running and actively used (menus opened, tabs clicked — real UI
   activity, the exact stimulus OSC feedback would answer).
4. **Process metadata.** No UDP sockets on `FL64.exe` in any `process_meta`
   snapshot, and no OSC-related values in `HKCU\Software\Image-Line` — the
   app neither listens nor has anything configured to send.

## Method (who did what)

The operator role was automated for this check: menu and dialog navigation
via `targets/fl-studio/operator_gui.py` (pyautogui), perception via the
built-in Windows OCR engine (`targets/fl-studio/ocr.ps1`), which returns
text with pixel bounding boxes — clickable without a vision model. The
settings dialog was closed without changing anything. apire itself never
touched FL: it listened only (capture above, zero frames).

## Consequence for the campaign

- Remove OSC from the hypothesis list; the WebView2/CDP surface remains
  FL's real observable API surface (see the M6 session section in
  ../README.md).
- A "passive protocol fuzzing without fuzzing" experiment needs a
  hypothesis with an observable channel; for FL 26 that means the embedded
  browser, process/pipe metadata, and log/file artifacts — not OSC.
