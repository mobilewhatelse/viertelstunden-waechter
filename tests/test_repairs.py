"""Consent under Repairs is an active choice: the switch "share_usage" never starts on.

repairs.py imports Home Assistant and voluptuous, so the unit test reads the form schema from the source (ast) instead."""
import ast
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "custom_components" / "viertelstunden_waechter" / "repairs.py"


def _share_defaults():
    """{class name: [default of every vol.Required/vol.Optional("share_usage", default=...)]}"""
    out = {}
    for cls in ast.parse(SRC.read_text(encoding="utf-8")).body:
        if not isinstance(cls, ast.ClassDef):
            continue
        for node in ast.walk(cls):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("Required", "Optional")
                    and node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value == "share_usage"):
                default = next((k.value for k in node.keywords if k.arg == "default"), None)
                out.setdefault(cls.name, []).append(ast.literal_eval(default) if default is not None else None)
    return out


class ShareConsentDefaultTests(unittest.TestCase):
    def test_both_questions_start_off(self):
        d = _share_defaults()
        self.assertEqual(d.get("ShareUsageFlow"), [False])
        self.assertEqual(d.get("ShareCheckFlow"), [False])

    def test_no_form_presets_consent(self):
        for name, defaults in _share_defaults().items():
            self.assertNotIn(True, defaults, name)


if __name__ == "__main__":
    unittest.main()
