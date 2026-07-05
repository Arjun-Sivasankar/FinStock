import ast
from pathlib import Path

SRC_ROOT = Path(__file__).parent.parent / "src" / "finstock"
FORBIDDEN_HTTP_METHODS = {"post", "put", "patch", "delete"}


def _requests_attr_calls(tree: ast.AST):
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr in FORBIDDEN_HTTP_METHODS
            and isinstance(node.value, ast.Name)
            and node.value.id == "requests"
        ):
            yield node


def test_trading212_client_only_uses_requests_get():
    path = SRC_ROOT / "clients" / "trading212.py"
    tree = ast.parse(path.read_text())
    offenders = list(_requests_attr_calls(tree))
    assert not offenders, (
        f"trading212.py must never call requests.{{post,put,patch,delete}}, "
        f"found at lines {[n.lineno for n in offenders]}"
    )


def test_no_order_placement_endpoint_referenced_anywhere():
    for path in SRC_ROOT.rglob("*.py"):
        text = path.read_text()
        assert "/equity/orders" not in text, (
            f"{path} references the order-placement endpoint /equity/orders"
        )


def test_only_notify_module_uses_requests_post():
    for path in SRC_ROOT.rglob("*.py"):
        if path.name == "notify.py":
            continue
        tree = ast.parse(path.read_text())
        offenders = list(_requests_attr_calls(tree))
        assert not offenders, (
            f"{path} calls requests.{{post,put,patch,delete}} at lines "
            f"{[n.lineno for n in offenders]} — only notify.py may do this"
        )
