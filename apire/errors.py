"""Typed errors.

Remcp contract: the library never calls SystemExit; every failure crossing
the tool layer is one of these, serialized in-band by server.py's @tool
wrapper. Policy violations (the evidence gate, the authorization gate) are
PolicyError — a refused claim is a policy outcome, not a crash.
"""

from __future__ import annotations


class ApiReError(Exception):
    """Base class. Subclasses set `code`."""

    code = "apire_error"

    def __init__(self, message: str, **context):
        super().__init__(message)
        self.message = message
        self.context = context

    def to_dict(self) -> dict:
        return {
            "ok": False,
            "target": self.context.pop("target", None),
            "method": self.context.pop("method", None),
            "reliability": "unreliable",
            "warnings": [],
            "error": {"code": self.code, "message": self.message, **self.context},
        }


class CaptureError(ApiReError):
    code = "capture_error"


class TransportError(ApiReError):
    code = "transport_error"


class RedactionError(ApiReError):
    code = "redaction_error"


class NormalizationError(ApiReError):
    code = "normalization_error"


class StoreError(ApiReError):
    code = "store_error"


class PolicyError(ApiReError):
    code = "policy_violation"


class UnsupportedError(ApiReError):
    code = "unsupported"

    def __init__(self, message: str, **context):
        context.setdefault("hint", "refusal over guessing; this action lands in a later milestone (docs/roadmap.md)")
        super().__init__(message, **context)


class ExportError(ApiReError):
    code = "export_error"
