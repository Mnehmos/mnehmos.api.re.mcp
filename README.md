# apire — passive API reverse engineering

**Reverse-engineer an application's API by watching it, never by poking it.**

apire is an MCP server that observes an application you are authorized to
inspect, reconstructs its HTTP endpoints, WebSocket/event surfaces, payload
schemas and process architecture from what the application already sends
and receives — and attaches a verifiable evidence trail to every single
claim it makes.

Most API discovery tools are active: they send requests, replay traffic,
fuzz endpoints. apire cannot. Not "is configured not to" — **cannot**: the
engine contains no network-transmission capability, the tool surface has no
send action, and a test in CI fails the build if either changes. You can
point it at a system without worrying that the tool itself will touch it.

> Governing rule: **observe applications, never impersonate them.**

---

## What it does

You use the application normally. apire watches from the side:

1. **Capture** — HTTP through a local passthrough proxy, browser/Chromium
   traffic through the DevTools attach channel, UDP/OSC traffic, process
   and module metadata, log files, or HAR/log files you already have.
2. **Label** — you mark what you were doing ("idle", "opened the project",
   "renamed a track"), turning each capture into an experimental condition.
3. **Correlate** — the differential engine compares labeled captures and
   finds what changed *only because of* what you did: endpoints that appear
   under one condition and never another, event types that always follow a
   specific action, and the heartbeat noise that is neither.
4. **Interpret** — an LLM proposes names for opaque things (`type: 47` →
   `plugin.catalog.updated`); deterministic evidence decides what those
   names are worth. A guess with no evidence behind it stays worth zero,
   and the graph says so.
5. **Export** — OpenAPI, AsyncAPI, JSON Schema, a protocol catalog, an
   architecture map, and a candidate MCP capability surface — each element
   stamped with its evidence level, confidence, and the captures that
   justify it.

## The guarantee: it cannot touch your target

- **No transmission capability.** There is no replay, send, or execute
  action anywhere in the tool surface, and the engine imports no HTTP
  client. A CI test scans the engine's code and fails the build on egress
  capability — that test is the product's constitution in executable form.
- **Credentials never reach disk.** Authorization headers, cookies, tokens
  and password-shaped values are removed or pseudonymized *before* a frame
  is stored. What the store learns is `Authorization: <REDACTED>`, never
  the credential. This is exercised on live third-party traffic in the
  benchmark suite, with zero-leak assertions.
- **Everything stays local.** Captures and findings live in a machine-local
  store that is gitignored by default.
- **Authorization is a required input.** Starting a capture requires a
  statement of what you are authorized to inspect; it is recorded with the
  session and shown in exports.

Read more: [docs/security-model.md](docs/security-model.md).

## The tools

Seven tools, each an action menu over one domain. Ask your agent in plain
language; it calls these.

| Tool | What it's for |
| ---- | ------------- |
| `api_re_capture` | Start/stop/label observation sessions (six capture transports) |
| `api_re_observations` | Browse what was seen; compare and correlate sessions |
| `api_re_protocol` | The reconstructed protocol: transports, endpoints, messages, events, schemas, errors |
| `api_re_architecture` | Processes, connections, services, trust boundaries |
| `api_re_evidence` | Claims with proof, contradictions, unknowns, proposed next experiments, the policy itself |
| `api_re_semantics` | Submit interpretations; attach evidence so they can earn confidence |
| `api_re_export` | OpenAPI, AsyncAPI, JSON Schema, protocol catalog, architecture map, candidate MCP surface |

## What you get out

Every export carries evidence per element. Elements that don't meet your
confidence floor go into a separate `speculative` section — they are never
silently mixed in with observed fact. Authentication is always described as
"existing application session; credential material redacted at ingestion".

A real specimen, reconstructed purely from passive observation of FL Studio
26, is committed here:
[targets/fl-studio/exports/mcp_candidate.json](targets/fl-studio/exports/mcp_candidate.json)
— six cloud-API capabilities at INFERRED or STRONGLY INFERRED, each citing
the observations behind it.

## The evidence model, briefly

| Level | Meaning |
| ----- | ------- |
| CONFIRMED | matches an authoritative source or verified by a human |
| OBSERVED | present in captured traffic; recomputable from a capture |
| STRONGLY INFERRED | corroborated across independent observations |
| INFERRED | supported by one body of evidence (shape, ordering, exclusivity) |
| HYPOTHESIS | a model's interpretation with weak support |
| UNKNOWN | seen, not yet understood — kept, not discarded |

The model proposes; the evidence decides. A model proposal by itself is
pinned at zero confidence until capture-derived evidence is verified
against the store — a claim that cannot re-derive from captured evidence
does not get stored. Contradictions are preserved and visible, not resolved
by decree. "I don't know" is an available answer, and the tool uses it:
`api_re_evidence unknowns` is a first-class feature.

## What it can and cannot see

**Can:** plain HTTP via the proxy; Chromium/WebView2 traffic via DevTools
attach (requires the app to expose a debug port at launch); UDP/OSC on a
port it is told to listen to; processes, modules, listening sockets, named
pipes (presence and names); log files; HAR/log archives.

**Cannot, by design:** TLS-tunneled traffic through a `CONNECT` proxy — an
opaque tunnel is unobservable, so apire refuses and records the refusal
rather than pretending. Named-pipe *messages* — a Windows pipe can only be
read by its server, so apire observes pipe presence and naming and says so
([ADR-008](docs/decisions/008-pipe-observation-without-interception.md)).
OSC from applications that don't speak it. Anything you haven't captured.

## Install and register

Requires Python 3.11+. Developed and tested on Windows; the capture paths
are platform-neutral (loopback proxy, file and log ingest, UDP listen),
with process metadata via a cross-platform library.

```bash
git clone https://github.com/Mnehmos/mnehmos.api.re.mcp
cd mnehmos.api.re.mcp
pip install -r requirements.txt
python server.py          # speaks MCP over stdio
```

Register with any MCP client (pin the interpreter, not a bare `python`):

```json
{
  "apire": {
    "command": "python",
    "args": ["/absolute/path/to/mnehmos.api.re.mcp/server.py"],
    "description": "Passive API reverse engineering. Observe applications, never impersonate them."
  }
}
```

Configuration (all optional): `APIRE_KB` (evidence store location),
`APIRE_REDACTION_SALT` (pseudonymize instead of redact), `APIRE_MAX_BODY_FETCH`.

## Example asks

- "Start a passive capture through the loopback proxy on port 8123, then
  tell me when the app has made ten requests."
- "Label that capture 'idle', take another one while I open the plugin
  browser, and diff them."
- "What did `message type 47` correlate with? Show me `api_re_evidence
  explain` for it."
- "Propose names for the unexplained observations and tell me which
  experiments would raise their confidence."
- "Export an OpenAPI document grounded only in what we actually observed,
  and list what went into the speculative section and why."

## Measured, not promised

- **Control benchmark** (deterministic reference app with a committed
  spec, including one field the documentation gets *wrong*): endpoints
  reconstructed at 1.000 precision/recall; the planted discrepancy is
  flagged; zero secrets. Runs in CI.
- **Ecological benchmark** (Gitea, scored against its own published
  spec): version-schema agreement 1.000, zero secrets — and on its first
  run it found and fixed two real engine defects that the controlled
  environment never could.

## For developers

The engineering documents — architecture, roadmap, evidence policy, ADRs
(including what was measured, what was falsified, and what was rejected and
why) — live in [docs/](docs/), starting with
[architecture.md](docs/architecture.md) and
[decisions/](docs/decisions/). Working conventions and session handoffs are
in [CLAUDE.md](CLAUDE.md) and [.agent/](.agent/).

## License

MIT — see [LICENSE](LICENSE). Read-only by design; the enforcement story is
in [docs/security-model.md](docs/security-model.md).
