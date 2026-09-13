"""Control reference application (docs/evaluation.md).

A local app with a committed OpenAPI spec it *mostly* follows. The planted
discrepancy: the spec documents `created_at: string(date)` on Project while
the app emits `created_ts: integer` (epoch seconds). The benchmark's
highest-value assertion is that the reconstruction follows observed
behavior and flags the divergence — evidence over documentation.

Stdlib only, deliberately: the control target must be deterministic and
dependency-free. Fixture credentials only (any real-looking secret in these
fixtures is a defect).
"""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

FIXTURE_TOKEN = "Bearer control-fixture-" + "token-0123456789abcdef"

PROJECTS = [
    {"id": 1, "name": "Demo Set", "created_ts": 1750000000, "track_count": 3},
    {"id": 2, "name": "Live Set", "created_ts": 1750100000, "track_count": 1},
]
TRACKS = {
    1: [
        {"id": 11, "name": "Kick", "type": "audio", "gain": 0.81},
        {"id": 12, "name": "Bass", "type": "midi", "note_count": 128},
        {"id": 13, "name": "Pad", "type": "audio", "gain": 0.55},
    ],
    2: [{"id": 21, "name": "Vox", "type": "audio", "gain": 0.7}],
}


class Handler(BaseHTTPRequestHandler):
    server_version = "ReferenceApp/1.0"

    def log_message(self, *args):  # deterministic output
        pass

    # ------------------------------------------------------------ helpers

    def _json(self, status: int, payload) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        return any(
            k.lower() == "authorization" and v.startswith("Bearer ") for k, v in self.headers.items()
        )

    # ------------------------------------------------------------ routes

    def do_GET(self):  # noqa: N802
        parsed = urlsplit(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/api/health":
            self._json(200, {"status": "ok"})
            return

        if path == "/api/projects":
            page = max(1, int(query.get("page", ["1"])[0]))
            per_page = max(1, int(query.get("per_page", ["10"])[0]))
            start = (page - 1) * per_page
            self._json(
                200,
                {
                    "items": PROJECTS[start : start + per_page],
                    "page": page,
                    "per_page": per_page,
                    "total": len(PROJECTS),
                },
            )
            return

        m = re.fullmatch(r"/api/projects/(\d+)", path)
        if m:
            project = next((p for p in PROJECTS if p["id"] == int(m.group(1))), None)
            if project is None:
                self._json(404, {"error": "not_found", "resource": "project"})
            else:
                self._json(200, project)
            return

        m = re.fullmatch(r"/api/projects/(\d+)/tracks", path)
        if m:
            pid = int(m.group(1))
            if not any(p["id"] == pid for p in PROJECTS):
                self._json(404, {"error": "not_found", "resource": "project"})
            else:
                self._json(200, {"items": TRACKS.get(pid, []), "total": len(TRACKS.get(pid, []))})
            return

        m = re.fullmatch(r"/api/tracks/(\d+)", path)
        if m:
            tid = int(m.group(1))
            track = next((t for ts in TRACKS.values() for t in ts if t["id"] == tid), None)
            if track is None:
                self._json(404, {"error": "not_found", "resource": "track"})
            else:
                self._json(200, track)
            return

        if path == "/api/secure/session":
            if not self._authorized():
                self._json(401, {"error": "unauthorized"})
            else:
                self._json(200, {"authenticated": True, "scopes": ["read"]})
            return

        self._json(404, {"error": "not_found", "resource": "path"})

    def do_POST(self):  # noqa: N802
        parsed = urlsplit(self.path)
        m = re.fullmatch(r"/api/projects/(\d+)/tracks", parsed.path)
        if not m:
            self._json(404, {"error": "not_found", "resource": "path"})
            return
        pid = int(m.group(1))
        if not any(p["id"] == pid for p in PROJECTS):
            self._json(404, {"error": "not_found", "resource": "project"})
            return
        if not self._authorized():
            self._json(401, {"error": "unauthorized"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._json(400, {"error": "invalid_json"})
            return
        if not isinstance(payload.get("name"), str) or not payload["name"]:
            self._json(422, {"error": "name_required"})
            return
        new_id = 100 + sum(len(v) for v in TRACKS.values())
        track = {"id": new_id, "name": payload["name"], "type": "audio", "gain": 0.5}
        TRACKS.setdefault(pid, []).append(track)
        self._json(201, track)


def make_server(port: int = 0) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    server = make_server(8210)
    print(f"reference app on http://127.0.0.1:{server.server_port}")
    server.serve_forever()
