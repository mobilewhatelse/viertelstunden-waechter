"""Data catalogue, version 1 (21.11.2026): short consent text with a link to the full list, and the version of the catalogue kept
with every Yes.

config_flow.py, repairs.py and coordinator.py import Home Assistant, so the unit test reads their calls from the source (ast);
rueckmeldung.py has no Home Assistant import and is tested directly."""

from __future__ import annotations

import ast
import json
import re
import sys
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "custom_components" / "viertelstunden_waechter"
# asyncio must be loaded without the integration folder on the path (it has its own select.py); an earlier test may have put it there
_path = list(sys.path)
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != PKG]
import asyncio  # noqa: E402,F401
sys.path[:] = _path
sys.path.insert(0, str(PKG))

import rueckmeldung as rm  # noqa: E402

FILES = {"strings": PKG / "strings.json", "de": PKG / "translations" / "de.json", "en": PKG / "translations" / "en.json"}
DIALOGS = {
    "finish": ("config", "step", "finish", "description"),
    "share_usage_question": ("issues", "share_usage_question", "fix_flow", "step", "confirm", "description"),
    "share_usage_check": ("issues", "share_usage_check", "fix_flow", "step", "confirm", "description"),
}
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _load(name: str) -> dict:
    return json.loads(FILES[name].read_text(encoding="utf-8"))


def _get(d: dict, path: tuple[str, ...]) -> str:
    for k in path:
        d = d[k]
    return d


def _strings(d, prefix=()):
    """Every text in a translation file with its path."""
    if isinstance(d, dict):
        for k, v in d.items():
            yield from _strings(v, prefix + (k,))
    elif isinstance(d, str):
        yield prefix, d


def _tree(name: str) -> ast.Module:
    return ast.parse((PKG / name).read_text(encoding="utf-8"))


def _show_forms(tree: ast.AST):
    """[(step_id, {placeholder keys} or None)] of every async_show_form call below `tree`."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "async_show_form":
            kw = {k.arg: k.value for k in node.keywords}
            step = kw["step_id"].value if isinstance(kw.get("step_id"), ast.Constant) else None
            ph = kw.get("description_placeholders")
            keys = {k.value for k in ph.keys if isinstance(k, ast.Constant)} if isinstance(ph, ast.Dict) else None
            out.append((step, keys))
    return out


def _class(tree: ast.Module, name: str) -> ast.ClassDef:
    return next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)


def _method(cls: ast.ClassDef, name: str) -> ast.FunctionDef:
    return next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)


def _calls(node: ast.AST) -> set[str]:
    """Dotted names of all calls below `node`, e.g. 'rm.zustimmung_merken'."""
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            parts = []
            while isinstance(f, ast.Attribute):
                parts.append(f.attr)
                f = f.value
            if isinstance(f, ast.Name):
                parts.append(f.id)
            out.add(".".join(reversed(parts)))
    return out


class PrivacyUrlTests(unittest.TestCase):
    def test_language_and_anchor(self):
        self.assertEqual(rm.privacy_url("de"), "https://www.aiwhatelse.eu/datenschutz/?lang=de#daten-teilen")
        self.assertEqual(rm.privacy_url("de-AT"), "https://www.aiwhatelse.eu/datenschutz/?lang=de#daten-teilen")
        self.assertEqual(rm.privacy_url("en"), "https://www.aiwhatelse.eu/datenschutz/?lang=en#daten-teilen")

    def test_fallback_english(self):
        for lang in (None, "", "fr", "nl"):
            self.assertIn("?lang=en#daten-teilen", rm.privacy_url(lang), lang)


class DialogPlaceholderTests(unittest.TestCase):
    """Every dialog whose text has {privacy_url} gets it from the code, otherwise Home Assistant cannot show the text."""

    def test_finish_passes_privacy_url(self):
        forms = [keys for step, keys in _show_forms(_tree("config_flow.py")) if step == "finish"]
        self.assertTrue(forms)
        for keys in forms:
            self.assertIn("privacy_url", keys or set())

    def test_repairs_pass_privacy_url(self):
        tree = _tree("repairs.py")
        for cls in ("ShareUsageFlow", "ShareCheckFlow"):
            forms = _show_forms(_class(tree, cls))
            self.assertTrue(forms, cls)
            for step, keys in forms:
                self.assertEqual(step, "confirm")
                self.assertIn("privacy_url", keys or set(), cls)

    def test_observe_only_keeps_devices(self):
        forms = _show_forms(_class(_tree("repairs.py"), "ObserveOnlyFlow"))
        self.assertEqual([keys for _, keys in forms], [{"devices"}])

    def test_texts_have_the_link(self):
        links = {"strings": "[What is sent when, and why]({privacy_url})", "en": "[What is sent when, and why]({privacy_url})",
                 "de": "[Was wann gesendet wird und warum]({privacy_url})"}
        for name in FILES:
            d = _load(name)
            for dialog, path in DIALOGS.items():
                text = _get(d, path)
                self.assertIn(links[name], text, (name, dialog))
                self.assertNotIn("aiwhatelse.eu/datenschutz", text, (name, dialog))   # the address comes only from the code
                self.assertEqual(set(PLACEHOLDER.findall(text)), {"privacy_url"}, (name, dialog))


class TranslationConsistencyTests(unittest.TestCase):
    def test_same_placeholders_in_all_three_files(self):
        texts = {name: dict(_strings(_load(name))) for name in FILES}
        self.assertEqual(set(texts["de"]), set(texts["strings"]))
        self.assertEqual(set(texts["en"]), set(texts["strings"]))
        for path, s in texts["strings"].items():
            want = sorted(PLACEHOLDER.findall(s))
            for name in ("de", "en"):
                self.assertEqual(sorted(PLACEHOLDER.findall(texts[name][path])), want, (name, ".".join(path)))

    def test_strings_equals_english(self):
        self.assertEqual(_load("strings"), _load("en"))

    def test_text_as_agreed(self):
        de, en = _load("de"), _load("en")
        for dialog, path in DIALOGS.items():
            t = _get(de, path)
            self.assertIn("Orte genauer als das Land", t, dialog)
            self.assertIn("beim Ausschalten werden die Wochendaten gelöscht, Tageswerte ohne Kennung lassen sich nicht löschen", t, dialog)
            e = _get(en, path)
            self.assertIn("places more precise than the country", e, dialog)
            self.assertIn("daily values without an id cannot be deleted", e, dialog)
        # those who shared before: note and what the switch does in ONE paragraph (it starts off, so confirming alone switches
        # sharing off); the rest as in the question, without its first paragraph
        first = {
            "de": "Sie teilen schon anonyme Daten, danke. Neu in 0.15: der Geräte-Check, einmal am Tag prüft der Wächter Ihre Geräte und "
                  "meldet, wenn etwas nicht stimmt. Bitte einmal bestätigen. Schalter an und bestätigen: weiter teilen, mit Geräte-Check. "
                  "Schalter aus und bestätigen: Das Teilen wird ausgeschaltet.",
            "en": "You already share anonymous data, thank you. New in 0.15: the device check, once a day the guard checks your devices "
                  "and tells you when something is wrong. Please confirm once. Switch on and confirm: keep sharing, with the device "
                  "check. Switch off and confirm: sharing is switched off.",
        }
        for name, d in (("de", de), ("en", en)):
            check, question = _get(d, DIALOGS["share_usage_check"]), _get(d, DIALOGS["share_usage_question"])
            head, _, rest = check.partition("\n\n")
            self.assertEqual(head, first[name])
            self.assertEqual(rest, question.split("\n\n", 2)[2], name)   # Gesendet … link, as in the question
            self.assertNotIn(question.split("\n\n", 1)[0], check, name)   # "Anonyme Daten teilen schaltet …" not twice
        for dialog in ("finish", "share_usage_question"):   # the preview of the device check stays
            self.assertIn("![Vorschau: Geräte-Check](/viertelstunden_waechter/vorschau/geraete-check-de.webp)", _get(de, DIALOGS[dialog]))
            self.assertIn("![Preview: device check](/viertelstunden_waechter/vorschau/geraete-check-en.webp)", _get(en, DIALOGS[dialog]))


class CatalogueTests(unittest.TestCase):
    def test_yes_keeps_the_version(self):
        usage = {"gefragt": True}
        rm.zustimmung_merken(usage)
        self.assertEqual(usage, {"gefragt": True, "check_ok": True, "katalog": rm.KATALOG})
        self.assertEqual(rm.KATALOG, 1)
        self.assertEqual(rm.katalog(usage), 1)

    def test_missing_value_is_tolerated(self):
        self.assertEqual(rm.katalog({}), 0)
        self.assertEqual(rm.katalog(None), 0)
        self.assertEqual(rm.katalog({"check_ok": True}), 0)   # agreed before the catalogue: as before
        self.assertEqual(rm.katalog({"katalog": "x"}), 0)
        self.assertEqual(rm.katalog({"katalog": None}), 0)

    def test_never_sent(self):
        d = rm.statistik("viertelstunden_waechter", "0.15.0", "2026.11", "k", "AT", "de", {}, "0-1", {"a": 1})
        self.assertNotIn("katalog", json.dumps(d))

    def test_every_yes_keeps_it(self):
        cls = next(n for n in _tree("coordinator.py").body if isinstance(n, ast.ClassDef) and any(
            isinstance(m, ast.FunctionDef) and m.name == "answer_usage" for m in n.body))
        self.assertIn("rm.zustimmung_merken", _calls(_method(cls, "answer_usage")))
        self.assertIn("rm.zustimmung_merken", _calls(_method(cls, "confirm_check")))
        self.assertIn("rm.katalog", _calls(_method(cls, "ask_usage_once")))   # the Yes of the set-up
        self.assertIn("rm.katalog", _calls(_method(cls, "consent_catalog")))
        src = (PKG / "config_flow.py").read_text(encoding="utf-8")
        self.assertIn('self._options["katalog"] = KATALOG', src)


if __name__ == "__main__":
    unittest.main()
