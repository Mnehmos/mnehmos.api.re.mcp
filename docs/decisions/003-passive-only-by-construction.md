# 003. Passive-only by construction

- **Status:** accepted
- **Date:** 2026-09-12

## Context

The tool's entire value proposition — safe to point at any application you are
authorized to inspect — depends on it being *impossible*, not forbidden, for
the engine to transmit requests or mutate targets. Prompt rules and review
checklists are hopes; capability absence is a fact.

## Decision

Three enforcement layers, in strength order:

1. **Elimination:** no send/replay/execute/modify action exists in the tool
   surface. The action vocabulary is the permission system.
2. **Engineering:** `tests/test_no_egress.py` AST-scans `apire/` (non-test
   code) for banned egress imports/calls (`requests`, `httpx`,
   `urllib.request`, `http.client`, `socket.connect*`, `subprocess` network
   use, bare `.send(` outside `apire/capture/`). Socket-touching code exists
   only inside `apire/capture/` under the connect policy: listeners accept;
   attach-mode connects only to user-designated inspection channels
   (DevTools port, ETW); never to application endpoints; never carrying
   reconstructed application payloads.
3. **Detection:** tool-surface test asserts registered schemas contain no
   transmission verbs, so the guarantee survives future "helpful" additions.

## Alternatives considered

- *Runtime egress firewall (sandbox the process):* rejected as primary —
  platform-dependent, blind to what a transport legitimately does, and would
  false-positive on passthrough proxying. Noted as an additional M6+ layer if
  attach transports multiply.
- *Policy-prompt-only ("the server is documented read-only"):* rejected —
  exactly the failure the bible names: a rule living only in weights/prompt.

## Consequences

- Passthrough proxying is the one sanctioned socket-write path: the proxy
  answers the application with the application's own observed exchange. This
  is documented in security-model's honesty section.
- Adding a transport always lands with its scan update in the same commit.
- Some features become structurally impossible (auto-replay, request
  templating, "try this payload"). That is the product.

## Review trigger

Any PR that adds an import the scanner must special-case, or any feature
request phrased as "the tool could also send…".
