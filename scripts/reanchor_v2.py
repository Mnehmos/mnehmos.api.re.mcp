"""Re-anchor claims after a normalizer key change (ADR-009).

The v2 normalizer put the host into HTTP canonical keys, so every HTTP
observation got a new id and every claim whose subject was one of them is
stranded (`explain` reports `subject_resolves: false`). This script rebuilds
the old ids from the stored frames using the v1 formulas, maps them to the
current ids, remaps provenance (observation ids and canonical keys), and
re-saves each claim through the normal policy gate — so a migration that
would attach evidence to something that no longer exists fails loudly
instead of silently.

Run: python scripts/reanchor_v2.py [--dry-run]
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apire import kb  # noqa: E402
from apire.normalize import canonical_key, observation_key_for_frame, path_template, _parse_query_names  # noqa: E402
from apire.store import Store  # noqa: E402


def _obs_id(key: str) -> str:
    return "obs_" + hashlib.sha256(key.encode()).hexdigest()[:16]


def _v1_key(frame: dict) -> str | None:
    """The pre-v2 key formulas, kept here (not in normalize) so the mapping
    stays stable as the normalizer evolves further."""
    kind = frame.get("kind_hint", "raw")
    transport = frame.get("transport", "unknown")
    payload = frame.get("payload", {}) or {}
    if kind == "http_request":
        url = str(payload.get("url", ""))
        path = url.split("?", 1)[0].split("//", 1)[-1].split("/", 1)[-1]
        path = "/" + path if not path.startswith("/") else path
        method = str(payload.get("method", "GET")).upper()
        return canonical_key(kind, transport, method, path_template(path), "query(" + ",".join(sorted(_parse_query_names(url))) + ")")
    if kind == "http_response":
        return canonical_key(kind, transport, "", path_template(str(payload.get("path", "/"))), str(payload.get("status", 0)))
    return None


def build_maps(store: Store) -> tuple[dict, dict]:
    id_map: dict[str, str] = {}
    key_map: dict[str, str] = {}
    for frame in store.iter_frames():
        old = _v1_key(frame)
        if old is None:
            continue
        new = observation_key_for_frame(frame)
        id_map[_obs_id(old)] = _obs_id(new)
        key_map[old] = new
    return id_map, key_map


def migrate(store: Store, dry_run: bool = False) -> dict:
    id_map, key_map = build_maps(store)
    moved, skipped, failed = [], [], []
    for claim in store.all_claims():
        subject = claim["subject"]
        if not subject.startswith("obs_") or store.find_observation(subject) is not None:
            continue  # not stranded
        new_subject = id_map.get(subject)
        if new_subject is None:
            skipped.append({"claim_id": claim["claim_id"], "value": claim["value"], "reason": "no stored frame produces the old subject"})
            continue
        provenance = []
        for prov in claim["provenance"]:
            p = dict(prov)
            artifact = p.get("artifact", "")
            if artifact.startswith("obs_"):
                p["artifact"] = id_map.get(artifact, artifact)
            ck = p.get("canonical_key", "")
            if ck.startswith("ck:"):
                p["canonical_key"] = key_map.get(ck, ck)
            provenance.append(p)
        if dry_run:
            moved.append({"claim_id": claim["claim_id"], "value": claim["value"], "from": subject, "to": new_subject})
            continue
        try:
            updated = kb.save_claim(
                store,
                subject=new_subject,
                kind=claim["kind"],
                value=claim["value"],
                confidence=claim["confidence"],
                provenance=provenance,
                note=(claim.get("note", "") + " | re-anchored to normalizer v2 keys").strip(" |"),
                claim_id=claim["claim_id"],
            )
            updated["history"].append(
                {"subject": subject, "re_anchored_utc": updated["updated_utc"], "reason": "normalizer v2 key change"}
            )
            store.upsert_claim(updated)
            moved.append({"claim_id": claim["claim_id"], "value": claim["value"], "from": subject, "to": new_subject})
        except Exception as exc:  # PolicyError and friends: report, never hide
            failed.append({"claim_id": claim["claim_id"], "value": claim["value"], "error": f"{type(exc).__name__}: {exc}"})
    return {"moved": moved, "skipped": skipped, "failed": failed, "map_size": len(id_map)}


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    store = Store()
    print(f"KB: {store.kb_path}  (normalizer v{getattr(store, '_stored_normalizer', '?')})")
    result = migrate(store, dry_run=dry)
    print(f"map entries: {result['map_size']}")
    for row in result["moved"]:
        verb = "would move" if dry else "moved"
        print(f"  {verb}: {row['claim_id']} {row['value']!r}  {row['from']} -> {row['to']}")
    for row in result["skipped"]:
        print(f"  SKIP: {row['claim_id']} {row['value']!r}: {row['reason']}")
    for row in result["failed"]:
        print(f"  FAIL: {row['claim_id']} {row['value']!r}: {row['error']}")
    print(f"{len(result['moved'])} moved, {len(result['skipped'])} skipped, {len(result['failed'])} failed")
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
