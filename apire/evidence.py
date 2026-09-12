"""Evidence envelope.

Remcp's contract, unchanged: warnings travel with the answer, each warning
states its impact, and an envelope's reliability is the worst of them.
Nothing important is reported only on stderr, because no MCP client shows
stderr to the model that needs it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Reliability = Literal["sound", "degraded", "unreliable"]

_RANK: dict[str, int] = {"sound": 0, "degraded": 1, "unreliable": 2}


@dataclass
class Warning_:
    code: str
    detail: str
    impact: Reliability = "degraded"

    def to_dict(self) -> dict:
        return {"code": self.code, "detail": self.detail, "impact": self.impact}


@dataclass
class Envelope:
    target: str
    method: str
    result: dict = field(default_factory=dict)
    warnings: list[Warning_] = field(default_factory=list)

    def warn(self, code: str, detail: str, impact: Reliability = "degraded") -> None:
        self.warnings.append(Warning_(code, detail, impact))

    @property
    def reliability(self) -> Reliability:
        worst = "sound"
        for w in self.warnings:
            if _RANK[w.impact] > _RANK[worst]:
                worst = w.impact
        return worst  # type: ignore[return-value]

    def to_dict(self, ok: bool = True) -> dict:
        out: dict[str, Any] = {
            "ok": ok,
            "target": self.target,
            "method": self.method,
            "reliability": self.reliability,
            "warnings": [w.to_dict() for w in self.warnings],
        }
        if ok:
            out["result"] = self.result
        return out
