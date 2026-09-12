"""apire -- passive API reverse engineering MCP server.

Governing rule: Observe applications. Never impersonate them.

There is no send/replay/execute/modify action anywhere on this surface; the
absence is the guarantee. Seven action-enum tools over one domain each, per
the workspace action-enum doctrine. The engine (apire/) does the work; this
file only wires, wraps, and serializes.

Run: python server.py   (stdio)
"""

from __future__ import annotations

import functools
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Callable, Literal

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from apire import __version__, kb, project, semantics  # noqa: E402
from apire.capture import create_listener  # noqa: E402
from apire.correlate import compare as correlate_compare  # noqa: E402
from apire.correlate import correlate as correlate_run  # noqa: E402
from apire.errors import ApiReError, PolicyError, UnsupportedError  # noqa: E402
from apire.evidence import Envelope  # noqa: E402
from apire.store import Store  # noqa: E402

mcp = FastMCP("apire")

MAX_RESPONSE_CHARS = int(os.environ.get("APIRE_MAX_RESPONSE_CHARS", "120000"))

_STORE: Store | None = None
_LISTENERS: dict[str, Any] = {}


def store() -> Store:
    global _STORE
    if _STORE is None:
        _STORE = Store()
    return _STORE


# --------------------------------------------------------------------------
# Tool plumbing (remcp contract)
# --------------------------------------------------------------------------


def _dump(payload: dict) -> str:
    text = json.dumps(payload, indent=1, default=str)
    if len(text) <= MAX_RESPONSE_CHARS:
        return text
    clipped = {
        "ok": payload.get("ok", True),
        "target": payload.get("target"),
        "method": payload.get("method"),
        "reliability": payload.get("reliability"),
        "warnings": (payload.get("warnings") or [])
        + [
            {
                "code": "response_clipped",
                "detail": (
                    f"the full response was {len(text):,} characters, over the "
                    f"{MAX_RESPONSE_CHARS:,} limit. Narrow the query (add a filter, "
                    "lower the limit, or ask about one capture) rather than "
                    "consuming the whole context window."
                ),
                "impact": "degraded",
            }
        ],
        "result": None,
    }
    return json.dumps(clipped, indent=1, default=str)


def tool(fn: Callable[..., dict]) -> Callable[..., str]:
    """Wrap a handler so no failure can propagate out of the tool layer."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> str:
        try:
            return _dump(fn(*args, **kwargs))
        except ApiReError as exc:
            return json.dumps(exc.to_dict(), indent=1, default=str)
        except (KeyboardInterrupt, SystemExit) as exc:
            return json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": "aborted",
                        "message": f"the call aborted ({type(exc).__name__}): {exc}",
                        "hint": "this is a bug in the engine, not in your request",
                    },
                },
                indent=1,
            )
        except MemoryError:
            return json.dumps(
                {"ok": False, "error": {"code": "out_of_memory", "message": "narrow the request"}},
                indent=1,
            )
        except BaseException as exc:  # noqa: BLE001 -- deliberate last resort
            tb = traceback.format_exc(limit=6)
            return json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": "internal_error",
                        "message": f"{type(exc).__name__}: {exc}",
                        "trace_tail": tb[-1500:],
                        "hint": "a bug in apire; the server is still alive",
                    },
                },
                indent=1,
            )

    return wrapper


def _caps(capture_ids: list[str]) -> list[str]:
    ids = [c.strip() for c in capture_ids if c and c.strip()]
    if ids:
        return ids
    return [c["capture_id"] for c in store().list_captures()]


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------


@mcp.tool()
@tool
def api_re_capture(
    action: Literal["start", "stop", "status", "list", "label", "note"],
    transport: Literal["file_ingest", "udp_observe", "process_meta", "http_proxy", "log_tail", "devtools_attach", "pipe_listen"] = "file_ingest",
    name: str = "",
    authorization_statement: str = "",
    hypothesis: str = "",
    capture_id: str = "",
    label: str = "",
    seq: int = 0,
    text: str = "",
    host: str = "127.0.0.1",
    port: int = 9000,
    path: str = "",
    hint: str = "",
) -> dict:
    """Control observation spans. start begins a capture (requires
    authorization_statement or APIRE_AUTHORIZATION_STATEMENT); label sets the
    experimental condition used by correlation; note anchors a human comment
    to a frame sequence. One-shot transports (file_ingest, process_meta) stop
    themselves and return when done."""
    st = store()
    env = Envelope(target=capture_id or "captures", method=f"capture.{action}")
    if action == "start":
        auth = authorization_statement or os.environ.get("APIRE_AUTHORIZATION_STATEMENT", "")
        listener = create_listener(transport)
        cap = st.start_capture(
            transport=transport,
            name=name or (Path(path).name if path else transport),
            authorization_statement=auth,
            hypothesis=hypothesis,
            instrument=f"{transport}/v{getattr(listener, 'version', 1)}",
        )
        status = listener.start(st, cap["capture_id"], host=host, port=port, path=path, hint=hint)
        _LISTENERS[cap["capture_id"]] = listener
        one_shot = bool(status.get("one_shot"))
        if one_shot:
            final = listener.stop()
            cap = st.stop_capture(cap["capture_id"])
            status = {**status, **final, "auto_stopped": True}
        else:
            cap = st.get_capture(cap["capture_id"])
        env.result = {"capture": cap, "listener": status}
        if cap["frame_count"] == 0:
            env.warn(
                "empty_capture",
                "the capture ended with zero frames; check the transport parameters (file exists? port bound? hint matches?)",
                "degraded",
            )
        return env.to_dict()
    if action == "stop":
        listener = _LISTENERS.pop(capture_id, None)
        lstatus = listener.stop() if listener else {"note": "no listener attached (one-shot or unknown)"}
        cap = st.stop_capture(capture_id)
        env.result = {"capture": cap, "listener": lstatus}
        return env.to_dict()
    if action == "status":
        if capture_id:
            env.result = {"capture": st.get_capture(capture_id), "listener": _LISTENERS[capture_id].status() if capture_id in _LISTENERS else None}
        else:
            env.result = {
                "captures": [
                    {k: c[k] for k in ("capture_id", "name", "label", "transport", "frame_count", "started_utc", "ended_utc")}
                    for c in st.list_captures()
                ],
                "live_listeners": [cid for cid in _LISTENERS],
            }
        return env.to_dict()
    if action == "list":
        env.result = {"captures": st.list_captures()}
        return env.to_dict()
    if action == "label":
        env.result = {"capture": st.label(capture_id, label, hypothesis or None)}
        return env.to_dict()
    if action == "note":
        env.result = {"capture": st.note(capture_id, seq, text)}
        return env.to_dict()
    raise UnsupportedError(f"capture action '{action}'")


@mcp.tool()
@tool
def api_re_observations(
    action: Literal["list", "inspect", "compare", "correlate"],
    capture_ids: list[str] = [],
    observation_id: str = "",
    kind: str = "",
    endpoint_prefix: str = "",
    limit: int = 50,
) -> dict:
    """Query the capture store. list returns deduplicated observations;
    inspect shows one in full with its claims; compare diffs 2-8 captures per
    canonical key; correlate adds exclusivity by condition label, periodic
    noise classification, and candidate signals."""
    st = store()
    env = Envelope(target=observation_id or ",".join(capture_ids) or "all", method=f"observations.{action}")
    if action == "list":
        obs = st.build_observations(_caps(capture_ids))
        rows = [o for o in obs.values() if (not kind or o["kind"] == kind) and (not endpoint_prefix or endpoint_prefix in o["endpoint_template"])]
        rows.sort(key=lambda o: -o["observation_count"])
        env.result = {
            "count": len(rows),
            "observations": [
                {
                    "observation_id": o["observation_id"],
                    "kind": o["kind"],
                    "transport": o["transport"],
                    "endpoint": o["endpoint_template"],
                    "count": o["observation_count"],
                    "captures": len(o["capture_refs"]),
                    "semantic": project.semantic_for(st, o["observation_id"]),
                    "shape": {k: v for k, v in list(o["shape"].items())[:12]},
                }
                for o in rows[:limit]
            ],
            "truncated": len(rows) > limit,
        }
        return env.to_dict()
    if action == "inspect":
        obs = st.find_observation(observation_id)
        if obs is None:
            raise ApiErrorNotFound(observation_id)
        env.result = {
            "observation": obs,
            "claims": kb.query(st, subject=observation_id),
            "redaction_note": "payloads shown were redacted at ingestion; reports are per frame in the manifest",
        }
        return env.to_dict()
    if action == "compare":
        env.result = correlate_compare(st, _caps(capture_ids))
        return env.to_dict()
    if action == "correlate":
        env.result = correlate_run(st, _caps(capture_ids))
        if env.result["warning_unlabeled"]:
            env.warn(
                "unlabeled_captures",
                "some captures have no condition label; exclusivity is meaningless without labels. Use api_re_capture action=label.",
                "degraded",
            )
        check = env.result.get("instrument_check", {})
        if check.get("mismatch"):
            env.warn(
                "instrument_version_mismatch",
                f"captures were taken with different instrument versions {check['distinct']}; "
                "'exclusive' signals may reflect the instrument, not the condition. "
                "Re-take the baseline with the same instrument before trusting candidates.",
                "unreliable",
            )
        return env.to_dict()
    raise UnsupportedError(f"observations action '{action}'")


class ApiErrorNotFound(ApiReError):
    code = "not_found"


@mcp.tool()
@tool
def api_re_protocol(
    action: Literal["transports", "endpoints", "messages", "events", "schemas", "errors"],
    capture_ids: list[str] = [],
    prefix: str = "",
    limit: int = 50,
) -> dict:
    """The reconstructed protocol, as projections of the evidence graph.
    transports/endpoints/messages are live; events/schemas/errors land in a
    later milestone (refusal over guessing)."""
    st = store()
    env = Envelope(target="protocol", method=f"protocol.{action}")
    caps = _caps(capture_ids)
    if action == "transports":
        env.result = {"transports": project.transports_seen(st, caps)}
        return env.to_dict()
    if action == "endpoints":
        rows = project.endpoints(st, caps, prefix)
        env.result = {"count": len(rows), "endpoints": rows[:limit], "truncated": len(rows) > limit}
        return env.to_dict()
    if action == "messages":
        rows = project.messages(st, caps, prefix)
        env.result = {"count": len(rows), "messages": rows[:limit], "truncated": len(rows) > limit}
        return env.to_dict()
    raise UnsupportedError(f"protocol action '{action}' lands in M5 (exporters milestone)")


@mcp.tool()
@tool
def api_re_architecture(
    action: Literal["processes", "connections", "services", "boundaries"],
    capture_ids: list[str] = [],
    hint: str = "",
) -> dict:
    """The observed deployment map: processes, listening sockets, module
    scans (from process_meta). services/boundaries land later."""
    st = store()
    env = Envelope(target="architecture", method=f"architecture.{action}")
    caps = _caps(capture_ids)
    if action == "processes":
        env.result = project.processes(st, caps, hint)
        if not env.result["process_count"]:
            env.warn("no_process_meta", "no process_meta capture found; run api_re_capture transport=process_meta first", "degraded")
        return env.to_dict()
    if action == "connections":
        env.result = project.connections(st, caps)
        return env.to_dict()
    raise UnsupportedError(f"architecture action '{action}' lands in M6")


@mcp.tool()
@tool
def api_re_evidence(
    action: Literal["query", "explain", "contradictions", "unknowns", "experiments", "policy"],
    subject: str = "",
    min_level: str = "",
    provenance_class: str = "",
    claim_id: str = "",
) -> dict:
    """The honesty surface: claims with provenance and verification records,
    open contradictions, uninterpreted observations, and the policy itself."""
    st = store()
    env = Envelope(target=subject or claim_id or "evidence", method=f"evidence.{action}")
    if action == "query":
        env.result = {"claims": kb.query(st, subject, min_level, provenance_class)}
        return env.to_dict()
    if action == "explain":
        env.result = semantics.review(st, claim_id)
        return env.to_dict()
    if action == "contradictions":
        rows = kb.contradictions(st, subject)
        env.result = {"count": len(rows), "contradictions": rows}
        return env.to_dict()
    if action == "unknowns":
        rows = kb.unknowns(st)
        env.result = {"count": len(rows), "unknowns": rows}
        return env.to_dict()
    if action == "policy":
        env.result = kb.policy()
        return env.to_dict()
    raise UnsupportedError("experiments (proposed discriminating observations) land in M5")


@mcp.tool()
@tool
def api_re_semantics(
    action: Literal["propose", "attach_evidence", "review", "link"],
    subject: str = "",
    proposed_name: str = "",
    rationale: str = "",
    evidence_refs: list[str] = [],
    claim_id: str = "",
    related_claim_ids: list[str] = [],
    provenance_json: str = "",
    confidence: float = 0.0,
) -> dict:
    """The interpretation valve. propose stores a semantic name at confidence
    0.00 (llm_proposal cap is zero); attach_evidence adds capture-derived,
    recomputable evidence to raise it — the policy verifies each class or
    rejects the write."""
    st = store()
    env = Envelope(target=subject or claim_id, method=f"semantics.{action}")
    if action == "propose":
        env.result = {"claim": semantics.propose(st, subject, proposed_name, rationale, evidence_refs)}
        return env.to_dict()
    if action == "attach_evidence":
        try:
            added = json.loads(provenance_json)
        except json.JSONDecodeError as exc:
            raise PolicyError(f"provenance_json is not valid JSON: {exc}")
        if not isinstance(added, list) or not added:
            raise PolicyError("provenance_json must be a non-empty JSON list of {class, ...} objects")
        env.result = {"claim": semantics.raise_confidence(st, claim_id, added, confidence)}
        return env.to_dict()
    if action == "review":
        env.result = semantics.review(st, claim_id)
        return env.to_dict()
    if action == "link":
        env.result = {"claim": semantics.link(st, claim_id, related_claim_ids)}
        return env.to_dict()
    raise UnsupportedError(f"semantics action '{action}'")


@mcp.tool()
@tool
def api_re_export(
    action: Literal["openapi", "asyncapi", "json_schema", "protocol_spec", "architecture", "mcp_candidate"],
    min_level: Literal["INFERRED", "STRONGLY_INFERRED", "OBSERVED", "CONFIRMED"] = "INFERRED",
    path: str = "",
    capture_ids: list[str] = [],
) -> dict:
    """Specification exports, projected from the evidence graph with each
    element carrying its level. Not implemented yet (M5): the evidence must
    exist before the exporter that flattens it."""
    raise UnsupportedError(
        f"export action '{action}' lands in M5 once protocol/architecture projections carry levels",
        available_now=["api_re_protocol", "api_re_architecture", "api_re_evidence"],
    )


if __name__ == "__main__":
    mcp.run()
