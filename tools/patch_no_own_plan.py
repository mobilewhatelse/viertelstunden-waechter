"""One-off: with a car planner chosen the dashboard shows only the planner's plan (kept for the record)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def edit(rel, pairs):
    p = ROOT / rel
    s = p.read_text(encoding="utf-8")
    for a, b in pairs:
        assert s.count(a) == 1, f"{rel}: {a[:80]}"
        s = s.replace(a, b)
    p.write_text(s, encoding="utf-8")


edit("custom_components/viertelstunden_waechter/dashboard.py", [
    ("Der Wächter rechnet ihn in die Prognose ein und begrenzt Spitzen weiter in Echtzeit; den eigenen Ladeplan des Wächters brauchen Sie dann nicht.",
     "Der Wächter rechnet ihn in die Prognose ein und begrenzt Spitzen weiter in Echtzeit. Mit einem Auto-Planer zeigt der Wächter keinen eigenen Ladeplan: entweder der Planer oder der Wächter."),
    ('        "own_plan": "Eigener Ladeplan des Wächters (mit Auto-Planer nicht nötig)", "planned_word"', '        "planned_word"'),
    ('        "own_plan": "The guard\'s own charge plan (not needed with a car planner)", "planned_word"', '        "planned_word"'),
    ('"""The charge plan section: the plan of the car planner when one is chosen (the guard\'s own plan steps back),\n    otherwise the guard\'s own plan as before."""',
     '"""The charge plan section: with a car planner chosen only the planner\'s plan (either the planner or the guard, never two plans),\n    otherwise the guard\'s own plan as before."""'),
])

edit("tests/test_dashboard.py", [
    ('            self.assertIn(IDS["charge_plan_enabled"], stats)                    # its switches stay (to turn it off)\n',
     '            self.assertNotIn(IDS["charge_plan_enabled"], stats)                 # no own plan, no own plan switches: either the planner or the guard\n'
     '            self.assertNotIn(IDS["charge_plan_execute"], stats)\n'),
])

DOC_EN_OLD = ("  has one, the windows with energy, highest power and the share from the sun - plus the line *Car plan in the forecast*\n"
              "  (connected, how many windows, until when). The guard's own plan steps back; its two switches stay below, to switch it off.\n"
              "  Without a car planner the card is the guard's own plan as before.\n")
DOC_EN_NEW = ("  has one, the windows with energy, highest power and the share from the sun - plus the line *Car plan in the forecast*\n"
              "  (connected, how many windows, until when). **Either the planner or the guard:** with a car planner the guard's own plan and its\n"
              "  two switches are not on the dashboard at all (they stay on the device page; switch *Calculate the charge plan* off there).\n"
              "  Without a car planner the card is the guard's own plan as before.\n")
edit("README.md", [(DOC_EN_OLD, DOC_EN_NEW)])

DOC_DE_OLD = ("  bis wann). Der eigene Plan des Wächters tritt zurück; seine zwei Schalter stehen darunter, damit man ihn ausschalten kann.\n"
              "  Ohne Auto-Planer ist die Karte wie bisher der eigene Plan des Wächters.\n")
DOC_DE_NEW = ("  bis wann). **Entweder der Planer oder der Wächter:** Mit Auto-Planer steht der eigene Plan des Wächters mit seinen zwei Schaltern gar nicht\n"
              "  im Dashboard (er bleibt auf der Geräteseite; dort *Ladeplan berechnen* ausschalten).\n"
              "  Ohne Auto-Planer ist die Karte wie bisher der eigene Plan des Wächters.\n")
edit("docs/ANLEITUNG.md", [(DOC_DE_OLD, DOC_DE_NEW)])

edit("CHANGELOG.md", [
    ("until when). The own plan's switches stay below so it can be switched off; one plan instead of two that disagree. Without a\n  planner the dashboard is unchanged.",
     "until when). **Either the planner or the guard:** with a car planner the guard's own plan and its switches are not on the dashboard\n  at all (one plan instead of two that disagree; they stay on the device page). Without a planner the dashboard is unchanged."),
])
print("ok")
