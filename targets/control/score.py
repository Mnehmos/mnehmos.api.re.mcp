"""Deterministic benchmark scorer (docs/evaluation.md).

Runs the control reference app, observes a scripted session through the
loopback proxy, exports the reconstruction, and scores it against the
committed ground truth. No LLM is involved in scoring: the reconstruction
follows observed behavior; the scorer compares documents.

Run: python targets/control/score.py
"""

from __future__ import annotations

import http.client
import importlib.util
import json
import re
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from apire.capture.http_proxy import HttpProxyListener  # noqa: E402
from apire.export import json_schema_document, openapi_document  # noqa: E402
from apire.store import Store  # noqa: E402

REFERENCE_DIR = Path(__file__).resolve().parent / "reference_app"
GROUND_TRUTH = REFERENCE_DIR / "openapi.json"

AUTHORIZATION = "benchmark run: local control application, synthetic credentials only"


def _load_app():
    spec = importlib.util.spec_from_file_location("reference_app", REFERENCE_DIR / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _normalize_path(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", path)


def _endpoint_set(document: dict) -> set[tuple[str, str]]:
    out = set()
    for path, item in document.get("paths", {}).items():
        for method in ("get", "post", "put", "patch", "delete", "head", "options"):
            if method in item:
                out.add((method.upper(), _normalize_path(path)))
    return out


def _drive_session(proxy_port: int, app_token: str) -> list[str]:
    """The scripted user session: exactly the documented flows, plus the
    planted-discrepancy reads and an unauthenticated refusal."""
    calls = [
        ("GET", "/api/health", None, {}),
        ("GET", "/api/projects?page=1&per_page=10", None, {}),
        ("GET", "/api/projects/1", None, {}),
        ("GET", "/api/projects/999", None, {}),
        ("GET", "/api/projects/1/tracks", None, {}),
        ("GET", "/api/tracks/11", None, {}),
        ("GET", "/api/secure/session", None, {}),
        ("GET", "/api/secure/session", None, {"Authorization": app_token}),
    ]
    statuses = []
    conn = http.client.HTTPConnection("127.0.0.1", proxy_port, timeout=10)
    for method, target, body, headers in calls:
        url = f"http://127.0.0.1:{conn.port}{target}" if False else target
        conn.request(method, f"http://{_origin_host()}{target}", body=body, headers=headers)
        resp = conn.getresponse()
        resp.read()
        statuses.append(f"{method} {target} -> {resp.status}")
    # POST with and without auth
    for headers in (
        {"Content-Type": "application/json", "Authorization": app_token},
        {"Content-Type": "application/json"},
    ):
        conn.request("POST", f"http://{_origin_host()}/api/projects/1/tracks", body='{"name":"Hat"}', headers=headers)
        resp = conn.getresponse()
        resp.read()
        statuses.append(f"POST /api/projects/1/tracks -> {resp.status}")
    conn.close()
    return statuses


_origin = {"host": "127.0.0.1:0"}


def _origin_host() -> str:
    return _origin["host"]


def run() -> dict:
    app = _load_app()
    server = app.make_server(0)
    _origin["host"] = f"127.0.0.1:{server.server_port}"
    threading.Thread(target=server.serve_forever, daemon=True).start()

    store = Store(root=tempfile.mkdtemp(prefix="apire_bench_"))
    cap = store.start_capture(transport="http_proxy", authorization_statement=AUTHORIZATION, instrument="http_proxy/v1")
    listener = HttpProxyListener()
    listener.start(store, cap["capture_id"], host="127.0.0.1", port=0)
    proxy_port = listener._sock.getsockname()[1]
    try:
        session = _drive_session(proxy_port, app.FIXTURE_TOKEN)
    finally:
        listener.stop()
        store.stop_capture(cap["capture_id"])
        server.shutdown()

    capture_ids = [cap["capture_id"]]
    exported = openapi_document(store, capture_ids)
    schemas = json_schema_document(store, capture_ids)
    ground_truth = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))

    expected = _endpoint_set(ground_truth)
    observed = _endpoint_set(exported)
    matched = expected & observed
    endpoint_recall = len(matched) / len(expected) if expected else 0.0
    endpoint_precision = len(matched) / len(observed) if observed else 0.0
    method_accuracy = len(matched) / len(observed) if observed else 0.0

    # schema metrics on the project-detail *response body* definition
    # (the planted discrepancy lives in that shape)
    project_def = next(
        (
            v
            for k, v in schemas["$defs"].items()
            if "api_projects" in k and "tracks" not in k and "response_200" in k
        ),
        None,
    ) or next((v for k, v in schemas["$defs"].items() if "api_projects" in k and "tracks" not in k), None)
    observed_props = set((project_def or {}).get("properties", {}))
    expected_props = set(ground_truth["components"]["schemas"]["Project"]["properties"])
    prop_precision = len(observed_props & expected_props) / len(observed_props) if observed_props else 0.0
    prop_recall = len(observed_props & expected_props) / len(expected_props) if expected_props else 0.0
    discrepancy_flagged = "created_at" in expected_props and "created_at" not in observed_props and "created_ts" in observed_props

    manifest = (Path(store.captures_dir) / cap["capture_id"] / "manifest.jsonl").read_text(encoding="utf-8")
    token_value = app.FIXTURE_TOKEN.split(" ", 1)[1]
    secrets_leaked = int(token_value in manifest or token_value in json.dumps(exported) or token_value in json.dumps(schemas))

    frames = store.frames(cap["capture_id"])
    requests = sum(1 for f in frames if f["kind_hint"] == "http_request")
    responses = sum(1 for f in frames if f["kind_hint"] == "http_response")

    result = {
        "endpoints_expected": len(expected),
        "endpoints_observed": len(observed),
        "endpoint_recall": round(endpoint_recall, 3),
        "endpoint_precision": round(endpoint_precision, 3),
        "method_accuracy": round(method_accuracy, 3),
        "schema_property_precision": round(prop_precision, 3),
        "schema_property_recall": round(prop_recall, 3),
        "spec_discrepancy_flagged": discrepancy_flagged,
        "secrets_leaked": secrets_leaked,
        "frames": len(frames),
        "requests_recorded": requests,
        "responses_recorded": responses,
        "session": session,
        "observed_properties": sorted(observed_props),
        "expected_properties": sorted(expected_props),
    }
    _print_report(result)
    return result


def _print_report(r: dict) -> None:
    print("apire control benchmark")
    print("=======================")
    print(f"  endpoints        expected {r['endpoints_expected']}  observed {r['endpoints_observed']}")
    print(f"  endpoint recall  {r['endpoint_recall']:.3f}")
    print(f"  endpoint prec.   {r['endpoint_precision']:.3f}")
    print(f"  method accuracy  {r['method_accuracy']:.3f}")
    print(f"  schema prop P/R  {r['schema_property_precision']:.3f} / {r['schema_property_recall']:.3f}")
    print(f"  discrepancy      {'FLAGGED' if r['spec_discrepancy_flagged'] else 'not flagged'}")
    print(f"  secrets leaked   {r['secrets_leaked']}")
    print(f"  frames           {r['frames']} ({r['requests_recorded']} req / {r['responses_recorded']} resp)")
    print(f"  observed project props: {r['observed_properties']}")
    print(f"  spec project props:     {r['expected_properties']}")
    print()
    for line in r["session"]:
        print(f"  {line}")


if __name__ == "__main__":
    out = run()
    ok = out["endpoint_recall"] >= 0.95 and out["endpoint_precision"] >= 0.95 and out["secrets_leaked"] == 0 and out["spec_discrepancy_flagged"]
    sys.exit(0 if ok else 1)
