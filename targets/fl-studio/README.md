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

## Campaign protocol

1. **Inventory session.** Install; then `process_meta` + `udp_observe` +
   `pipe_listen` to inventory processes, modules, pipes, sockets, and traffic
   while idle. Output: the first architecture map (all claims HYPOTHESIS or
   better, each with its captures).
2. **Hypothesis sessions** (one issue each, stated before capture):
   - H1 — FL Studio's built-in OSC server emits traffic that correlates with
     UI actions and is observable passively.
   - H2 — the MIDI-scripting host (Python) exposes a scripting bridge
     surface with a message vocabulary.
   - H3 — plugin bridge processes exchange structured messages over
     pipes/shared memory visible to `pipe_listen`.
   - H4 — project operations (open/save) are mirrored in observable IPC.
3. **Differential batteries** (human-performed, labeled): open project /
   select channel / rename channel twice with names of different lengths /
   open plugin browser / rescan plugins / install plugin. Each battery is a
   capture with a condition label and action notes anchored to frame
   sequences.
4. **Interpretation valve.** Opaque observations (`type: 47`) get proposals;
   differential evidence raises or declines them; contradictions are kept.
5. **Audit.** A fresh session (not the one that built the map) runs
   `api_re_evidence explain` on every STRONGLY_INFERRED+ claim and attacks it
   with `contradictions`. The map is accepted only if the audit fails to
   break it.

## Deliverable

An `api_re_export mcp_candidate` capability surface for FL Studio — the
"FL Studio MCP" arm of the capability foundry — plus the honest measure:
how much of the surface remains UNKNOWN, stated plainly.

## Rules

- The tool never sends anything to FL Studio. The human clicks; the tool
  watches.
- OSC/pipes used by *other* software on the machine may appear in captures;
  they are noise until correlated, and correlating them is the correlator's
  job, not a reason to widen capture filters beyond the authorized
  statement.
