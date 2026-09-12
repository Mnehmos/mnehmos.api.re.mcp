# 007. Storage: append-only capture store + atomic JSON evidence KB

- **Status:** accepted
- **Date:** 2026-09-12

## Context

Two kinds of state with opposite requirements: raw frames (immutable evidence,
append-heavy, potentially large) and claims (revised over time, small, must
never lose history). remcp's `kb.py` already solved the claim side: atomic
writes with one-generation `.bak`, schema versioning, history on revision,
`StoreError` on corruption.

## Decision

- **Capture store** (`APIRE_CAPTURES_DIR`, default `./apire_kb/captures/`):
  per-capture manifest JSONL (append-only) + content-addressed frame blobs
  (`sha256[:16]`), size-capped by `APIRE_MAX_CAPTURE_BYTES`. Frames are
  immutable; corrections happen downstream in normalization, never by editing
  evidence.
- **Evidence KB** (`APIRE_KB`, default `./apire_kb/kb.json`): remcp kb
  contract verbatim — schema version field, atomic temp-file + `os.replace`
  writes with `.bak`, revision history arrays, downgrade notes, `PolicyError`
  on unverifiable claims.
- **Exports**: written where the user aims them (default `./exports/`);
  evidence stores never leave the machine; exports carry no secret material
  by construction and are the intended shareable artifact.

## Alternatives considered

- *SQLite everywhere:* rejected for v1 — remcp's JSON store is proven,
  greppable, diffable, and its failure modes (atomicity, corruption detection)
  are already handled and tested. Revisit if frame counts make JSONL manifests
  slow (blobs are already content-addressed, so migration is contained).
- *Mutable frame store (dedupe by overwrite):* rejected — evidence is
  append-only or it is not evidence.

## Consequences

- Recompute-from-store is always possible (the M4 property test depends on
  this): delete the KB, rebuild every claim from captures alone, get the same
  graph.
- Disk usage is bounded by capture caps; pruning is a human decision on
  machine-local data, never automatic.

## Review trigger

Capture manifests exceeding comfortable JSONL sizes, or a multi-session
workflow needing concurrent writers (coordination that is not formalized
races — lock or serialize before that day).
