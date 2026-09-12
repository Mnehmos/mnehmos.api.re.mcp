"""The governing rule in executable form.

Observe applications. Never impersonate them.

This scan fails the build if the engine package acquires a
network-transmission capability. In M0 the engine does not exist yet, so the
scan asserts the ban list is still specified in docs/security-model.md — the
rule must not quietly rot while the code is being born. From M1 onward it
AST-scans every non-test module in apire/.

Do not weaken this test. Extend the ban list instead (ADR-003).
"""

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

BANNED_IMPORTS = {
    "requests",
    "httpx",
    "aiohttp",
    "urllib.request",
    "http.client",
    "ftplib",
    "smtplib",
    "telnetlib",
    "pycurl",
}

BANNED_CALLS = {
    "create_connection",
    "connect",
    "connect_ex",
}

# The only module allowed to touch sockets, under the connect policy of ADR-003.
SOCKET_CAPABLE_MODULES = {"capture"}


def _module_allows_sockets(rel: Path) -> bool:
    return len(rel.parts) > 0 and rel.parts[0] in SOCKET_CAPABLE_MODULES


def _iter_engine_modules():
    engine = REPO / "apire"
    if not engine.is_dir():
        return
    for py in engine.rglob("*.py"):
        rel = py.relative_to(engine)
        if any(part.startswith("test") for part in rel.parts):
            continue
        yield rel, py


def _scan_module(rel: Path, py: Path, violations: list) -> None:
    tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
    allows_sockets = _module_allows_sockets(rel)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if alias.name in BANNED_IMPORTS or root in {b.split(".")[0] for b in BANNED_IMPORTS}:
                    violations.append(f"{rel}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            if node.module in BANNED_IMPORTS or root in {b.split(".")[0] for b in BANNED_IMPORTS}:
                violations.append(f"{rel}: from {node.module} import ...")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            if attr in BANNED_CALLS and not allows_sockets:
                # socket-family calls outside the sanctioned capture modules
                if "socket" in ast.unparse(node.func).lower() or attr == "create_connection":
                    violations.append(f"{rel}:{node.lineno}: call .{attr}() outside apire/capture/")


def test_ban_list_is_still_specified():
    """While apire/ does not exist, the spec must still carry the ban list."""
    security = (REPO / "docs" / "security-model.md").read_text(encoding="utf-8")
    for banned in ["requests", "httpx", "urllib.request", "http.client", "socket.connect"]:
        assert banned in security, f"ban list lost '{banned}' from docs/security-model.md"
    adr3 = (REPO / "docs" / "decisions" / "003-passive-only-by-construction.md").read_text(encoding="utf-8")
    assert "test_no_egress" in adr3, "ADR-003 no longer names its enforcing test"


def test_engine_has_no_egress_capability():
    violations = []
    modules = list(_iter_engine_modules())
    for rel, py in modules:
        _scan_module(rel, py, violations)
    assert not violations, (
        "egress capability detected in the engine (governing rule: observe, "
        "never impersonate):\n  " + "\n  ".join(violations)
    )


def test_engine_either_absent_or_socket_code_confined():
    """Socket-touching code may only live in apire/capture/."""
    engine = REPO / "apire"
    if not engine.is_dir():
        return  # M0: nothing to confine yet
    for py in engine.rglob("*.py"):
        rel = py.relative_to(engine)
        if any(part.startswith("test") for part in rel.parts):
            continue
        src = py.read_text(encoding="utf-8")
        if "import socket" in src and not _module_allows_sockets(rel):
            raise AssertionError(f"{rel}: imports socket outside apire/capture/")


if __name__ == "__main__":
    sys.exit(0)
