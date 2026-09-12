"""End-to-end MCP wire test over stdio (standalone: python tests/wire_test.py).

Exercises the failure paths deliberately and, after each one, checks the
server is still answering — a tool call never crashes the stdio loop.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from mcp_client import Client  # noqa: E402

FAILURES: list[str] = []
PASSES: list[str] = []
AUTH = "wire test: synthetic local observation, authorized"


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        PASSES.append(name)
        print(f"PASS  {name}")
    else:
        FAILURES.append(f"{name}: {detail}")
        print(f"FAIL  {name}  {detail}")


def main() -> int:
    c = Client()
    try:
        hs = c.handshake()
        check("handshake", isinstance(hs, dict) and "result" in hs, str(hs)[:200])

        tools = c.list_tools()
        check(
            "seven tools registered",
            sorted(tools) == sorted(
                [
                    "api_re_capture",
                    "api_re_observations",
                    "api_re_protocol",
                    "api_re_architecture",
                    "api_re_evidence",
                    "api_re_semantics",
                    "api_re_export",
                ]
            ),
            str(tools),
        )

        # --- happy path: policy self-description
        pol = c.call("api_re_evidence", {"action": "policy"})
        check(
            "policy self-description",
            isinstance(pol, dict) and pol.get("ok") and any(c_["class"] == "llm_proposal" and c_["cap"] == 0.0 for c_ in pol["result"]["provenance_classes"]),
            str(pol)[:300],
        )

        # --- failure path: capture without authorization statement
        r = c.call("api_re_capture", {"action": "start", "transport": "process_meta"})
        check(
            "capture start without authorization is refused",
            isinstance(r, dict) and r.get("ok") is False and r["error"]["code"] == "policy_violation",
            str(r)[:300],
        )
        probe = c.call("api_re_evidence", {"action": "policy"})
        check("server alive after refusal", isinstance(probe, dict) and probe.get("ok") is True)

        # --- happy path: one-shot process snapshot
        r = c.call("api_re_capture", {"action": "start", "transport": "process_meta", "name": "wire-inventory", "authorization_statement": AUTH})
        check(
            "process_meta capture",
            isinstance(r, dict) and r.get("ok") is True and r["result"]["capture"]["frame_count"] > 0,
            str(r)[:300],
        )
        cap_id = r["result"]["capture"]["capture_id"] if isinstance(r, dict) and r.get("ok") else ""

        # --- observations + architecture read back
        obs = c.call("api_re_observations", {"action": "list", "capture_ids": [cap_id]})
        check("observations list", isinstance(obs, dict) and obs.get("ok") and obs["result"]["count"] >= 2, str(obs)[:300])

        arch = c.call("api_re_architecture", {"action": "processes", "hint": ""})
        check("architecture processes", isinstance(arch, dict) and arch.get("ok") and arch["result"]["process_count"] > 3, str(arch)[:300])

        # --- failure path: unsupported action (refusal over guessing)
        r = c.call("api_re_export", {"action": "openapi"})
        check(
            "export refuses until M5",
            isinstance(r, dict) and r.get("ok") is False and r["error"]["code"] == "unsupported",
            str(r)[:300],
        )
        probe = c.call("api_re_evidence", {"action": "policy"})
        check("server alive after unsupported", isinstance(probe, dict) and probe.get("ok") is True)

        # --- failure path: bad enum value -> schema rejection, server survives
        r = c.call("api_re_capture", {"action": "exfiltrate"})
        rejected = isinstance(r, dict) and (
            "mcp_error" in r or r.get("ok") is False or "validation error" in json.dumps(r)
        )
        check("invalid enum rejected", rejected, str(r)[:300])
        probe = c.call("api_re_evidence", {"action": "policy"})
        check("server alive after invalid enum", isinstance(probe, dict) and probe.get("ok") is True)

        # --- failure path: unknown observation
        r = c.call("api_re_observations", {"action": "inspect", "observation_id": "obs_nope"})
        check(
            "unknown observation refused",
            isinstance(r, dict) and r.get("ok") is False and r["error"]["code"] == "not_found",
            str(r)[:300],
        )
        probe = c.call("api_re_evidence", {"action": "policy"})
        check("server alive after not_found", isinstance(probe, dict) and probe.get("ok") is True)

        # --- semantics valve: proposal is stored at zero confidence
        obs_list = c.call("api_re_observations", {"action": "list", "capture_ids": [cap_id], "kind": "process_meta"})
        if isinstance(obs_list, dict) and obs_list.get("ok") and obs_list["result"]["count"]:
            oid = obs_list["result"]["observations"][0]["observation_id"]
            r = c.call("api_re_semantics", {"action": "propose", "subject": oid, "proposed_name": "wire.process.inventory", "rationale": "wire test reading"})
            check(
                "proposal stored at zero confidence",
                isinstance(r, dict) and r.get("ok") is True and r["result"]["claim"]["confidence"] == 0.0,
                str(r)[:300],
            )
        else:
            check("proposal stored at zero confidence", False, "no observations to propose against")
    finally:
        c.close()

    print(f"\n{len(PASSES)} passed, {len(FAILURES)} failed")
    for f in FAILURES:
        print(" -", f)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
