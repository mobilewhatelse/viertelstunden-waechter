"""One-off: HACS is the built-in Marketplace since Home Assistant 2026.11 (kept for the record).

The catalog (`hacs/default`), `hacs.json` and the HACS validation action keep their names; only the user-facing text changes.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def edit(rel, pairs, regex=()):
    p = ROOT / rel
    s = p.read_text(encoding="utf-8")
    for a, b in pairs:
        assert s.count(a) >= 1, f"{rel}: {a[:60]}"
        s = s.replace(a, b)
    for a, b in regex:
        s = re.sub(a, b, s)
    p.write_text(s, encoding="utf-8")


COMMUNITY_EN = [(r"\(HACS, `", "(community, `"), (r"\(HACS\)", "(community)"), (r"\(HACS;", "(community;")]
COMMUNITY_DE = [(r"\(HACS, `", "(Community, `"), (r"\(HACS\)", "(Community)")]

edit("README.md", [
    ("in the HACS default list, in daily use", "in the Marketplace (HACS default list), in daily use"),
    ("(no HACS needed for them)", "(nothing from the Marketplace needed for them)"),
    ("Open HACS, search for **Viertelstunden-Wächter**", "Open **Settings → Marketplace** (called HACS before Home Assistant 2026.11), search for **Viertelstunden-Wächter**"),
    ("(a new entry can take some hours to reach HACS)", "(a new entry can take some hours to reach the Marketplace)"),
    ("HACS → ⋮ → Custom repositories → this repository", "Marketplace → ⋮ → Custom repositories → this repository"),
    ("the integration is public and in the HACS default list (0.13.2)", "the integration is public and in the Marketplace (HACS default list, 0.13.2)"),
], COMMUNITY_EN)

edit("docs/ANLEITUNG.md", [
    ("(dafür ist **kein HACS** nötig)", "(dafür ist **nichts aus dem Marketplace** nötig)"),
    ("1. HACS öffnen, nach **Viertelstunden-Wächter** suchen", "1. **Einstellungen → Marketplace** öffnen (bis Home Assistant 2026.10 hieß das HACS), nach **Viertelstunden-Wächter** suchen"),
    ("(Wird es in HACS noch nicht gefunden", "(Wird es im Marketplace noch nicht gefunden"),
    ("HACS → ⋮ → Benutzerdefinierte Repositories", "Marketplace → ⋮ → Benutzerdefinierte Repositories"),
], COMMUNITY_DE)

edit("docs/COMPATIBILITY.md", [("core or HACS, version", "core or community integration from the Marketplace, version")], COMMUNITY_EN)
edit("docs/KOMPATIBILITAET.md", [("Home Assistant oder HACS, Version", "Home Assistant oder Community-Integration aus dem Marketplace, Version")], COMMUNITY_DE)
edit(".github/ISSUE_TEMPLATE/bug-report.md", [
    ("(HACS or `manifest.json`)", "(Settings → Marketplace, or `manifest.json`)"),
    ("via HACS integration X", "via community integration X from the Marketplace"),
])
edit(".github/ISSUE_TEMPLATE/device-test-report.md", [("(core or HACS, version)", "(core or community integration from the Marketplace, version)")])
edit("docs/PUBLISHING.md", [("State: 2026-11-03.", "Note: since Home Assistant 2026.11 HACS is built in as the **Marketplace**; the catalog (`hacs/default`),\n"
                                                   "`hacs.json` and the HACS validation action keep their names, so nothing below changes for publishing.\n\nState: 2026-11-03.")])
print("ok")
