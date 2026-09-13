# 009. Host belongs in HTTP canonical keys

- **Status:** implemented 2026-09-12
- **Date:** 2026-09-12

## Implementation (2026-09-12)

- HTTP keys include the host (v2 normalizer); observations carry a `host`
  field for disambiguation.
- The KB header records `normalizer_version`; a mismatch surfaces as a
  `normalizer_version_mismatch` warning on every read tool until the file is
  re-saved under the current version.
- `scripts/reanchor_v2.py` rebuilds v1-era ids from the stored frames (v1
  formulas preserved in the script, not in the normalizer), remaps subjects,
  provenance artifacts and canonical keys, and re-saves each claim through
  the policy gate — so a migration that would attach evidence to something
  that no longer exists fails loudly.
- Live migration: **9 claims moved, 1 skipped, 0 failed** — the skip is the
  historical waveform claim whose subject predates even v1 (`explain` still
  flags it `subject_resolves: false`; it stays as the honest record).

## Incident found while migrating (now a guard)

The first migration wrote correctly, then a **long-lived background server**
(finished OSC listening window) blind-wrote its stale in-memory KB over the
result — last-writer-wins clobbering, silently. The store now fails closed:
if the KB file changed on disk since this session loaded it, `_save_kb`
raises `StoreError` with instructions instead of overwriting. Two live
sessions can no longer lose each other's writes; restart-and-retry is the
recovery. (ADR-007's review trigger — concurrent writers — fired; the
fail-closed guard is the first step, a lockfile or merge is the future fix.)

## Context

Canonical keys for HTTP observations currently hash (kind, transport,
method, path template, query-names-or-status). The **host is not part of the
key**, so two different services with the same path merge into one
observation. Observed live during the FL-Cloud capture: `GET /tag` appears
on both `search.cloud.image-line.com` and `www.googletagmanager.com`;
`obs_bf6918062788c2b6` merges them. Same risk class: any `/health`, `/api`,
`/config` shared across hosts.

## Decision

Host **must** join the key (and the endpoint label) — but not yet. The
deliberate deferral:

1. Claims are anchored to observation ids derived from keys. Re-keying now
   would strand every HTTP-subject claim (this session demonstrated the cost
   twice: the waveform claim was re-anchored after the status change, and the
   exact-status change stranded another that now shows
   `subject_resolves: false`).
2. The re-anchoring procedure exists and is proven (propose against the
   current observation, attach the same evidence, link the old claim).
3. Doing it as a deliberate, isolated change — with the re-anchor pass in the
   same commit — is cheaper than doing it mid-campaign under audit.

## Plan when triggered

1. Normalizer: include `host` in `canonical_key` for `http_request` /
   `http_response`; include host in `endpoint_template` labels.
2. Re-anchor every claim whose subject starts `obs_` and stops resolving
   (the `explain` output now lists them via `subject_resolves: false`).
3. Bump the normalizer version into the KB header so future key changes are
   *detectable without archaeology* (the missing piece this ADR uncovered).

## Review trigger

Next FL campaign session, or any target with multi-host captures, or the
first time a merged `/tag`-class observation confuses an audit.
