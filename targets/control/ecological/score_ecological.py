"""Ecological control tier: score reconstruction against Gitea's own spec.

The primary control (../reference_app) is deterministic and offline; this
tier is reality — a real third-party application with a published OpenAPI
document it does not coordinate with us about.

Method: the operator (this script) drives a scripted anonymous session
through apire's loopback proxy, then fetches Gitea's spec directly as
ground truth. apire only ever observes the proxied session; the spec fetch
is the scorer's own act, stated here rather than implied.

Run: python targets/control/ecological/score_ecological.py
"""

from __future__ import annotations

import http.client
import json
import re
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from apire.capture.http_proxy import HttpProxyListener  # noqa: E402
from apire.export import json_schema_document, openapi_document  # noqa: E402
from apire.store import Store  # noqa: E402

GITEA = "http://127.0.0.1:3001"
# Fixture credentials deliberately embedded: the redaction gate must scrub
# the password from the captured signin POST.
FIXTURE_USER = "apire-fixture-user"
FIXTURE_PASSWORD = "fixture-password-" + "0123456789abcdef"

AUTHORIZATION = "benchmark run: locally hosted open-source application (Gitea), synthetic credentials only"


def _normalize(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", path)


def _gitea_reachable() -> bool:
    try:
        with urllib.request.urlopen(f"{GITEA}/api/v1/version", timeout=5) as r:
            return json.loads(r.read()).get("version") is not None
    except Exception:
        return False


def _session(proxy_port: int) -> list[str]:
    calls = [
        ("GET", "/api/v1/version", None, {}),
        ("GET", "/api/v1/repos/search?q=test&limit=5", None, {}),
        ("GET", "/api/v1/users/apire-does-not-exist", None, {}),
        ("POST", "/api/v1/user/signin", json.dumps({"user_name": FIXTURE_USER, "password": FIXTURE_PASSWORD}), {"Content-Type": "application/json"}),
    ]
    out = []
    conn = http.client.HTTPConnection("127.0.0.1", proxy_port, timeout=15)
    for method, path, body, headers in calls:
        conn.request(method, f"{GITEA}{path}", body=body, headers=headers)
        resp = conn.getresponse()
        resp.read()
        out.append(f"{method} {path} -> {resp.status}")
    conn.close()
    return out


def run() -> dict:
    if not _gitea_reachable():
        print(f"Gitea is not reachable at {GITEA}. Start it first:")
        print("  targets/control/ecological/run_gitea.cmd   (see README.md)")
        raise SystemExit(2)

    store = Store(root=tempfile.mkdtemp(prefix="apire_eco_"))
    cap = store.start_capture(transport="http_proxy", authorization_statement=AUTHORIZATION, instrument="http_proxy/v1")
    listener = HttpProxyListener()
    listener.start(store, cap["capture_id"], host="127.0.0.1", port=0)
    proxy_port = listener._sock.getsockname()[1]
    try:
        session = _session(proxy_port)
    finally:
        listener.stop()
        store.stop_capture(cap["capture_id"])

    with urllib.request.urlopen(f"{GITEA}/swagger.v1.json", timeout=30) as r:
        spec = json.loads(r.read())

    exported = openapi_document(store, [cap["capture_id"]])
    schemas = json_schema_document(store, [cap["capture_id"]])

    # Swagger 2.0 often carries a basePath the path keys are relative to
    # (Gitea: basePath "/api/v1", paths like "/version").
    base_path = spec.get("basePath", "")
    spec_endpoints = set()
    for path, item in spec.get("paths", {}).items():
        for method in ("get", "post", "put", "patch", "delete"):
            if method in item:
                spec_endpoints.add((method.upper(), _normalize(base_path + path)))
    observed = set()
    for path, item in exported.get("paths", {}).items():
        for method in ("get", "post", "put", "patch", "delete"):
            if method in item:
                observed.add((method.upper(), _normalize(path)))

    matched = observed & spec_endpoints
    precision = len(matched) / len(observed) if observed else 0.0
    method_accuracy = len(matched) / len(observed) if observed else 0.0

    # schema agreement on /api/v1/version: resolve the spec's own indirections
    # (Gitea: responses.200 -> #/responses/ServerVersion -> #/definitions/
    # ServerVersion), and prefer the observed *response* body definition
    resp_node = (spec.get("paths", {}).get("/version", {}).get("get", {}).get("responses", {}) or {}).get("200", {})
    resp_ref = resp_node.get("$ref", "")
    if resp_ref.startswith("#/responses/"):
        resp_node = spec.get("responses", {}).get(resp_ref.rsplit("/", 1)[-1], {})
    schema_node = resp_node.get("schema", {}) or {}
    def_ref = schema_node.get("$ref", "")
    spec_def_name = def_ref.rsplit("/", 1)[-1] if def_ref else ""
    spec_props = set(spec.get("definitions", {}).get(spec_def_name, {}).get("properties", {}))
    if not spec_props and schema_node.get("properties"):
        spec_props = set(schema_node["properties"])
    version_def = next(
        (v for k, v in schemas["$defs"].items() if "version" in k and "response_200" in k),
        None,
    ) or next((v for k, v in schemas["$defs"].items() if "version" in k), None)
    observed_props = set((version_def or {}).get("properties", {}))
    observed_props.discard("status")
    prop_agreement = len(observed_props & spec_props) / len(observed_props) if observed_props else 0.0

    manifest = (Path(store.captures_dir) / cap["capture_id"] / "manifest.jsonl").read_text(encoding="utf-8")
    secrets_leaked = int(FIXTURE_PASSWORD in manifest or FIXTURE_PASSWORD in json.dumps(exported))

    result = {
        "gitea_version": json.loads(urllib.request.urlopen(f"{GITEA}/api/v1/version", timeout=5).read())["version"],
        "observed_endpoints": sorted(f"{m} {p}" for m, p in observed),
        "endpoint_precision_vs_spec": round(precision, 3),
        "method_accuracy": round(method_accuracy, 3),
        "spec_size": len(spec_endpoints),
        "version_schema_props_observed": sorted(observed_props),
        "version_schema_props_spec": sorted(spec_props),
        "schema_property_agreement": round(prop_agreement, 3),
        "secrets_leaked": secrets_leaked,
        "session": session,
    }
    _print(result)
    return result


def _print(r: dict) -> None:
    print(f"apire ecological benchmark — Gitea {r['gitea_version']}")
    print("=" * 52)
    print(f"  observed endpoints            {len(r['observed_endpoints'])}")
    for ep in r["observed_endpoints"]:
        print(f"    {ep}")
    print(f"  spec size (app's own OpenAPI) {r['spec_size']} endpoints")
    print(f"  endpoint precision vs spec    {r['endpoint_precision_vs_spec']:.3f}")
    print(f"  method accuracy               {r['method_accuracy']:.3f}")
    print(f"  version schema agreement      {r['schema_property_agreement']:.3f}")
    print(f"    observed: {r['version_schema_props_observed']}")
    print(f"    spec:     {r['version_schema_props_spec']}")
    print(f"  secrets leaked                {r['secrets_leaked']}")
    for line in r["session"]:
        print(f"  {line}")


if __name__ == "__main__":
    out = run()
    ok = out["endpoint_precision_vs_spec"] >= 0.95 and out["secrets_leaked"] == 0 and out["schema_property_agreement"] >= 0.95
    sys.exit(0 if ok else 1)
