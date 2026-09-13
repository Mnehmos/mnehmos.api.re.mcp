"""apire.

First principle: Observe applications. Never impersonate them.

The engine is a pure library: zero MCP imports, zero egress capability
(enforced by tests/test_no_egress.py), typed errors only, in-band evidence.
The only module permitted to touch sockets lives in apire/capture/ under the
connect policy of ADR-003.
"""

__version__ = "0.4.0"
