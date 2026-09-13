# 008. Named pipes: observation without interception

- **Status:** accepted
- **Date:** 2026-09-12

## Context

The original transport roster advertised `pipe_listen` — "listen on a
named pipe and capture messages". Investigating it against reality (FL
Studio's plugin bridges were the motivating target) produced an
inconvenience:

**A Windows named pipe can only be read by its server.** There is no
supported way for a third party to attach to an existing pipe pair; to
receive messages you must *be* the server, which means the application must
already be configured to connect to a pipe you create. For an application
you cannot reconfigure (the entire challenge-target premise), a passive
pipe listener cannot exist. Building one would have meant injection — the
one thing this project must never do.

## Decision

1. Remove `pipe_listen` from the transport vocabulary. The tool surface is
   the permission system (ADR-005); advertising an action that can only
   fail — or worse, that would require injection to succeed — is dishonest.
2. Observe pipes through **presence and naming**: `process_meta` now
   enumerates `\\.\pipe\` and emits `named_pipes` (system-wide summary) plus
   per-entity `pipe_present` frames for hint matches. Pipe *names* are
   themselves evidence: they reveal which components exist and how they are
   versions/named, and "pipe X appeared only when the target ran" is a
   differential fact.
3. Message-level pipe capture returns to the roadmap only under the
   proxy pattern: if a target is ever configured (by its operator) to
   connect to an operator-hosted pipe endpoint, a passthrough listener is
   sanctioned exactly like `http_proxy`. That is a target-specific
   configuration act, not a general capability.

## Alternatives considered

- *Implement `pipe_listen` with a Windows API tap:* no supported API exists
  short of kernel/ETW machinery with injection-grade privilege; rejected.
- *Advertise it and fail at runtime with a helpful error:* rejected —
  the surface promises what the engine cannot deliver.
- *Drop pipe observation entirely:* rejected — names and presence are real,
  obtainable evidence, and the differential correlator consumes them.

## Consequences

- The tool-surface transport enum shrinks (six transports), and
  docs/architecture's module table now lists what exists.
- FL Studio's H3 hypothesis narrows honestly: bridge *existence* and pipe
  *names* are observable; bridge *messages* are not, unless a future
  session runs with an operator-configured pipe endpoint.
- The ADR is itself evidence: a capability was removed because reality said
  so, and the removal is recorded where the next agent will look.
