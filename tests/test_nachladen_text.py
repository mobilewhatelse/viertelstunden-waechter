"""0.16.0: the description of *Recharge from* (battery device) says what the FAQ says (Storage/Victron: "recharging belongs to the
following after a real release"): from that time the old minimum SOC comes back and the battery charges from the grid, only after a
real release, never without an intervention, and only with *Put the previous values back*. At most two sentences."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "custom_components" / "viertelstunden_waechter"
DOCS = Path(__file__).resolve().parents[1] / "docs"


def _load(rel: str) -> dict:
    return json.loads((PKG / rel).read_text(encoding="utf-8"))


def _descriptions(d, path=()):
    """Every data_description.recharge_at with its path."""
    if isinstance(d, dict):
        for k, v in d.items():
            if k == "recharge_at" and path and path[-1] == "data_description":
                yield path, v
            else:
                yield from _descriptions(v, path + (k,))


def _sentences(text: str) -> int:
    t = text.replace("z. B.", "zB").replace("e.g.", "eg")
    return len(re.findall(r"[.!?](?:\s|$)", t))


WANT = {
    "de": ("echten Freigabe", "alten Wert", "aus dem Netz", "Vorherige Werte wiederherstellen", "Mindest-Ladestand folgt dem Ladestand zurück",
           "ohne vorherigen Eingriff"),
    "en": ("real release", "old value", "from the grid", "Put the previous values back", "Minimum SOC follows the charge back up",
           "without an intervention before"),
}


class RechargeDescriptionTests(unittest.TestCase):
    def test_both_steps_in_all_files(self):
        for f, lang in (("strings.json", "en"), ("translations/de.json", "de"), ("translations/en.json", "en")):
            found = list(_descriptions(_load(f)))
            self.assertEqual(len(found), 2, f)          # battery: set up and reconfigure
            for path, text in found:
                for word in WANT[lang]:
                    self.assertIn(word, text, (f, ".".join(path)))
                self.assertLessEqual(_sentences(text), 2, text)

    def test_switch_names_match_the_dialog(self):
        """The names in the text are the field names of the same dialog."""
        for f in ("translations/de.json", "translations/en.json"):
            for path, text in _descriptions(_load(f)):
                d = _load(f)
                for k in path[:-1]:
                    d = d[k]
                for field in ("restore_original", "restore_stepwise"):
                    self.assertIn(d["data"][field], text, (f, field))

    def test_faq_uses_the_same_words(self):
        self.assertIn("echten Freigabe", (DOCS / "HAEUFIGE_FRAGEN.md").read_text(encoding="utf-8"))
        self.assertIn("real release", (DOCS / "FAQ.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
