"""The configuration shown in the status attribute and in diagnostics never contains a password."""
import ast
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "custom_components" / "viertelstunden_waechter" / "coordinator.py"


def _is_secret():
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    ns = {"Any": object}
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "SECRET_MARKERS" for t in node.targets):
            exec(compile(ast.Module([node], []), "c", "exec"), ns)
        if isinstance(node, ast.FunctionDef) and node.name == "is_secret":
            exec(compile(ast.Module([node], []), "c", "exec"), ns)
    return ns["is_secret"]


class SecretTest(unittest.TestCase):
    def test_is_secret(self):
        f = _is_secret()
        for key in ("evcc_password", "evcc_site_password", "api_token", "client_secret", "API_KEY"):
            self.assertTrue(f(key), key)
        for key in ("evcc_url", "name", "power_entity", "evcc_loadpoint"):
            self.assertFalse(f(key), key)

    def test_configuration_filters(self):
        self.assertIn("not is_secret(k)", SRC.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
