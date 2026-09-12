# 004. Redaction at ingestion (not at display, not at export)

- **Status:** accepted
- **Date:** 2026-09-12

## Context

Captured traffic is full of credentials by definition (that is what
authentication looks like on the wire). Any design that stores raw and
redacts later has a window — a crash dump, a committed store, a debug print —
in which the secret exists as the secret.

## Decision

The redactor is a mandatory gate between capture and persistence; frames are
redacted **before** their bytes are written anywhere. Two modes:

- **Pseudonymize** (salt set): credential-shaped values →
  `HMAC-SHA256(salt, value)[:16]`, prefix `~:`. Equality survives (session
  correlation across captures), the value does not.
- **Redact** (no salt): `<REDACTED>`, full stop.

The salt never enters the KB; `sha256(salt)[:16]` is stored as a fingerprint
so salt changes are detected and warned. Every redacted frame carries a
redaction report (classes fired, counts — never values).

Pseudonyms are KB-internal: exporters project only redacted/derived data and
never rehydrate pseudonyms into exports.

## Alternatives considered

- *Redact at display/export only:* rejected — the raw secret persists and
  every new consumer is a new leak path.
- *Store raw encrypted at rest:* rejected for v1 — key management becomes the
  new root secret, and "encrypted" storage of credentials reconstructs the
  threat we exist to remove. Revisit only if a use case demands post-hoc
  deep inspection, via a new ADR.
- *Model-judged redaction (ask the LLM what looks secret):* rejected — the
  spec table decides; the model's judgment is at best a proposal for extending
  the table.

## Consequences

- Values whose *shape* we fail to recognize inside opaque blobs may persist
  (stated blind spot; surfaced via redaction reports and `unknowns`).
- Pseudonym correlation breaks if the salt is lost — fingerprint warning
  makes this visible instead of silent.
- Tests assert on stored bytes, not on API return values (the store is the
  thing that must be clean).

## Review trigger

Any code path that writes frames without passing the redactor; any new
credential class observed in the wild (extend the table).
