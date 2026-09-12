"""The surface is the permission system: absence is a guarantee.

Static scan of server.py: exactly the seven documented tools, every action
enum free of transmission verbs, no action parameter that could be mistaken
for a way to send something to the target.
"""

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SERVER = Path(__file__).resolve().parent.parent / "server.py"

EXPECTED_TOOLS = {
    "api_re_capture",
    "api_re_observations",
    "api_re_protocol",
    "api_re_architecture",
    "api_re_evidence",
    "api_re_semantics",
    "api_re_export",
}

# Verbs that would mean the tool can impersonate the application.
FORBIDDEN_ACTION_VERBS = {
    "send",
    "replay",
    "execute",
    "modify",
    "inject",
    "post",
    "put",
    "delete",
    "call",
    "request",
    "proxy",
}


def _tool_functions():
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and any(
            isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "tool" for d in node.decorator_list
        ):
            yield node


def _literal_strings(annotation) -> list[str]:
    out = []
    node = annotation
    if isinstance(node, ast.Subscript) and getattr(node.value, "id", "") == "Literal":
        for elt in node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                out.append(elt.value)
    return out


def test_exactly_seven_tools():
    names = {fn.name for fn in _tool_functions()}
    assert names == EXPECTED_TOOLS, f"surface drifted: {sorted(names)}"


def test_no_transmission_verbs_in_action_enums():
    violations = []
    for fn in _tool_functions():
        for arg in fn.args.args:
            if arg.arg != "action" or arg.annotation is None:
                continue
            for action in _literal_strings(arg.annotation):
                head = action.lower()
                if head in FORBIDDEN_ACTION_VERBS:
                    violations.append(f"{fn.name}: action '{action}'")
    assert not violations, "transmission-shaped action appeared: " + ", ".join(violations)


def test_no_optional_parameters_in_tool_signatures():
    """Optional[...] emits anyOf:[T,null], which strict providers reject
    (workspace action-enum doctrine). Plain defaults only. `action` itself is
    required by design; every other parameter carries a plain default."""
    violations = []
    for fn in _tool_functions():
        params = fn.args.args
        defaults = list(fn.args.defaults)
        first_default_index = len(params) - len(defaults)
        for i, arg in enumerate(params):
            if i == 0:  # action
                continue
            if i < first_default_index:
                violations.append(f"{fn.name}.{arg.arg}: parameter without a default")
            ann = ast.unparse(arg.annotation) if arg.annotation else ""
            if "Optional" in ann or "None" in ann:
                violations.append(f"{fn.name}.{arg.arg}: {ann}")
    assert not violations, "signature rule broken: " + ", ".join(violations)


def test_tools_are_wrapped_by_the_exception_boundary():
    for fn in _tool_functions():
        decorators = {getattr(d, "id", None) or getattr(d.func, "id", None) for d in fn.decorator_list}
        assert "tool" in decorators, f"{fn.name} is missing the @tool boundary"
