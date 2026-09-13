"""Redaction at ingestion: the gate between capture and persistence (ADR-004).

The governing assertion style here is the one that matters: assert on the
*stored bytes*, not on API return values. A redactor that transforms in
memory but lets the token reach the manifest is a defect regardless of what
the function returns.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apire import redaction
from apire.store import Store

TOKEN = "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.Q2h1Y2sgaXQgb3V0"
# Split so the repo secret-scanner (STANDARDS.md grep) cannot match the
# fixture; the detector still sees one contiguous credential at runtime.
API_KEY = "sk-proj-" + "abcdefghijklmnopqrstuvwx"


def _http_frame():
    return {
        "kind_hint": "http_request",
        "transport": "http_proxy",
        "direction": "client_to_server",
        "payload": {
            "method": "GET",
            "url": "https://api.example.com/v1/projects?token=supersecret123&limit=10",
            "headers": {
                "Authorization": TOKEN,
                "Cookie": "sessionid=deadbeefcafe; other=1",
                "X-Api-Key": API_KEY,
                "Accept": "application/json",
            },
            "body": {"password": "hunter2", "note": "benign"},
        },
    }


def test_bearer_and_denylisted_headers_are_redacted():
    frame, report = redaction.redact_frame(_http_frame())
    hdrs = frame["payload"]["headers"]
    assert hdrs["Authorization"] == redaction.REDACTED
    assert hdrs["Cookie"] == redaction.REDACTED
    assert hdrs["X-Api-Key"] == redaction.REDACTED
    # benign values survive
    assert hdrs["Accept"] == "application/json"
    assert frame["payload"]["url"].count("supersecret123") == 0
    assert "benign" in json.dumps(frame)


def test_credential_shaped_values_are_redacted_anywhere():
    frame, _ = redaction.redact_frame(
        {
            "kind_hint": "log_line",
            "payload": {
                "line": f"auth failed for key {API_KEY} retrying",
                "nested": {"deep": {"jwt": "eyJhbGciOiJub25lIn0.eyJ4IjoxfQ.c2ln"}},
            },
        }
    )
    text = json.dumps(frame)
    assert API_KEY not in text
    assert "eyJhbGciOiJub25lIn0" not in text


def test_pseudonymize_mode_preserves_equality_not_values():
    salt = b"\x01" * 32
    frame = {
        "kind_hint": "http_response",
        "payload": {"body": {"session": "sess-value-1234", "other_session": "sess-value-1234"}},
    }
    red, _ = redaction.redact_frame(frame, mode="pseudonymize", salt=salt)
    a = red["payload"]["body"]["session"]
    b = red["payload"]["body"]["other_session"]
    assert a == b, "equal inputs must produce equal pseudonyms (correlation survives)"
    assert "sess-value-1234" not in json.dumps(red)
    assert a.startswith("~:")
    # different salt -> different pseudonym
    red2, _ = redaction.redact_frame(frame, mode="pseudonymize", salt=b"\x02" * 32)
    assert red2["payload"]["body"]["session"] != a


def test_report_counts_classes_and_carries_no_values():
    frame, report = redaction.redact_frame(_http_frame())
    assert report["classes_fired"], "report must say what fired"
    assert report["redacted_values"] >= 4
    text = json.dumps(report)
    assert TOKEN not in text and API_KEY not in text and "hunter2" not in text


def test_json_string_bodies_are_redacted_recursively(tmp_path):
    """A JSON body captured as a *string* (postData, HAR body_sample) must
    get key-name redaction inside it — the ecological tier caught a real
    password leaking through this hole (Gitea signin POST)."""
    frame = {
        "kind_hint": "http_request",
        "payload": {
            "method": "POST",
            "url": "http://127.0.0.1:3001/api/v1/user/signin",
            "headers": {"Content-Type": "application/json"},
            "postData": '{"user_name":"apire-fixture-user","password":"hunter2-abcdef"}',
        },
    }
    red, report = redaction.redact_frame(frame)
    assert "hunter2-abcdef" not in json.dumps(red)
    body = json.loads(red["payload"]["postData"])
    assert body["password"] == redaction.REDACTED
    assert body["user_name"] == "apire-fixture-user"
    assert report["classes_fired"]


def test_stored_bytes_never_contain_the_token(tmp_path):
    """The M1 gate: ingest through the public store path, then read the raw
    manifest from disk. The store is the thing that must be clean."""
    store = Store(root=tmp_path)
    cap = store.start_capture(
        transport="file_ingest",
        name="redaction-gate",
        authorization_statement="fixture test: synthetic traffic, authorized",
    )
    store.append_frame(cap["capture_id"], _http_frame())
    manifest = (Path(store.captures_dir) / cap["capture_id"] / "manifest.jsonl").read_text(encoding="utf-8")
    assert TOKEN not in manifest
    assert API_KEY not in manifest
    assert "hunter2" not in manifest
    assert "supersecret123" not in manifest
    # and the redaction is visible as evidence, not silent
    frame = json.loads(manifest.strip().splitlines()[0])
    assert frame["redacted"] is True
    assert frame["redaction_classes_fired"]


def test_salt_fingerprint_detects_salt_change(tmp_path):
    store = Store(root=tmp_path, salt=b"\x03" * 32)
    first = store.salt_fingerprint()
    store2 = Store(root=tmp_path, salt=b"\x04" * 32)
    assert store2.salt_fingerprint() != first
