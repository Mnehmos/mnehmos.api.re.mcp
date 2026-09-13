# Ecological control tier — a real application (Gitea)

The primary control (`../reference_app`) is deterministic and built for us.
This tier is reality: **Gitea 1.27.3**, an unrelated open-source application
that publishes its own OpenAPI document (Swagger 2.0) and does not
coordinate with us about anything.

Chosen over `open5e-api` for runnability, not for softness: a single
binary, sqlite, no service dependencies — the ecological *measurement*
should not require a fifteen-minute setup.

## Setup + run

```text
1. download (once):  curl -L -o targets/control/ecological/installers/gitea.exe \
      https://dl.gitea.com/gitea/1.27.3/gitea-1.27.3-windows-4.0-amd64.exe
2. start it:         targets\control\ecological\run_gitea.cmd
3. score it:         python targets/control/ecological/score_ecological.py
```

The work directory (`work/`, sqlite + repos) and the downloaded binary are
gitignored. Gitea is configured with `INSTALL_LOCK` and no registration —
an anonymous, unconfigured instance: exactly what a stranger sees.

## Method

The scorer (operator role) drives a scripted anonymous session **through
apire's loopback proxy**, then fetches Gitea's spec directly as ground
truth. apire only ever observes the proxied session; the spec fetch is the
scorer's own act. The session deliberately includes fixture credentials in
the signin POST so the redaction gate is exercised on real traffic.

## Results (2026-09-12, first run)

| Metric | Result |
| ------ | ------ |
| Observed endpoints | 4 (`GET /version`, `GET /repos/search`, `GET /users/{name}` probe, `POST /user/signin` probe) |
| Spec size | 482 endpoints |
| Endpoint precision vs spec | 0.500 — see findings |
| Version schema agreement | **1.000** (observed `{version}` vs spec `{version}`, after resolving the spec's two-hop `$ref` indirection) |
| Secrets leaked | **0** (the fixture password was scrubbed from the signin POST body) |

### Findings (this tier earned its place on day one)

1. **Proxy sent no `Host` header upstream.** The reference app never
   noticed (Python's http.server is lenient); Gitea's Go server answered
   every request with 400. Fixed: the proxy rebuilds `Host` from the
   absolute-form target. Regression test: `test_host_header_is_rebuilt_for_the_upstream`.
2. **Credentials inside JSON-*string* bodies were not redacted.** The
   signin POST captured as a string (`postData`) bypassed key-name rules;
   the fixture password reached the manifest. Fixed: JSON strings are
   parsed and redacted recursively (`test_json_string_bodies_are_redacted_recursively`).
3. **Word-like path segments are not collapsed** (`/users/apire-does-not-exist`
   stays literal instead of `/users/{var}`), so the user-lookup probe counts
   as a precision miss. This is a genuine ambiguity from a single sighting —
   a username and a static segment look identical. The refinement is a
   **two-sighting rule** (collapse a word-like segment only when two
   different values have been observed at that position), which is a
   normalizer v3 change and therefore a deliberate act with a re-anchor pass
   (ADR-009's procedure). Recorded, not rushed.
4. The other precision miss is `POST /user/signin`, which Gitea itself
   answers 404 — a probed route that is not API surface. Honest metric:
   observed paths that the app does not implement count against us.

Precision is expected to be below the primary control's 1.000 here: this is
a stranger's application and the session is four calls, not a curated
battery. The tier's job is to find real defects — it found two on the first
run, both now fixed with regression tests.
