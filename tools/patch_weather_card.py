"""One-off: the weather card shows only a short "still learning" line until the correction can say something (kept for the record)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def edit(rel, pairs):
    p = ROOT / rel
    s = p.read_text(encoding="utf-8")
    for a, b in pairs:
        assert s.count(a) == 1, f"{rel}: {a[:90]}"
        s = s.replace(a, b)
    p.write_text(s, encoding="utf-8")


edit("custom_components/viertelstunden_waechter/dashboard.py", [
    ('        "weather_active": "Die Korrektur wirkt jetzt auf die Prognose.",',
     '        "weather_learning": "Wetterkorrektur: lernt noch", "weather_of14": "von 14 Tagen mit Temperatur",\n'
     '        "weather_active": "Die Korrektur wirkt jetzt auf die Prognose.",'),
    ('        "weather_active": "The correction is changing the forecast now.",',
     '        "weather_learning": "Weather correction: still learning", "weather_of14": "of 14 days with temperature",\n'
     '        "weather_active": "The correction is changing the forecast now.",'),
    ('''        "{% else %}**" + x["weather_outdoor"] + ":** {{ w.get('temperature_now') if w.get('temperature_now') is not none else '–' }} °C"
        " · {{ w.get('forecast_hours', 0) }} " + x["weather_hours"] + "\\n\\n"
        "**" + x["weather_learned"] + ":** {{ w.get('days', 0) }} " + x["weather_days"] + "\\n\\n"
        "**" + x["weather_heat"] + ":** {{ '%.2f' | format(w.get('heat_kw_per_k', 0)) }} kW/K · "
        "**" + x["weather_cool"] + ":** {{ '%.2f' | format(w.get('cool_kw_per_k', 0)) }} kW/K · "
        "**" + x["weather_fit"] + ":** {{ '%.2f' | format(w.get('r2', 0)) }}\\n\\n"
        "{% if w.get('active') %}" + x["weather_active"] + "{% else %}" + x["weather_waiting"] + "{% endif %}"
        "{% endif %}"''',
     '''        "{% elif not w.get('active') %}**" + x["weather_learning"] + "** · {{ w.get('days', 0) }} " + x["weather_of14"] + ""
        "{% else %}**" + x["weather_outdoor"] + ":** {{ w.get('temperature_now') if w.get('temperature_now') is not none else '–' }} °C"
        " · {{ w.get('forecast_hours', 0) }} " + x["weather_hours"] + "\\n\\n"
        "**" + x["weather_learned"] + ":** {{ w.get('days', 0) }} " + x["weather_days"] + "\\n\\n"
        "**" + x["weather_heat"] + ":** {{ '%.2f' | format(w.get('heat_kw_per_k', 0)) }} kW/K · "
        "**" + x["weather_cool"] + ":** {{ '%.2f' | format(w.get('cool_kw_per_k', 0)) }} kW/K · "
        "**" + x["weather_fit"] + ":** {{ '%.2f' | format(w.get('r2', 0)) }}\\n\\n"
        "" + x["weather_active"] + ""
        "{% endif %}"'''),
])

edit("CHANGELOG.md", [
    ("- **Dashboard cleaned up, graphics first** (user feedback): fewer cards;",
     "- **Weather card says only what it knows:** until the correction can say something (fewer than 14 whole days with temperature, or a\n"
     "  slope of zero) the card is one line, *Weather correction: still learning, 3 of 14 days with temperature*; the numbers (heating,\n"
     "  cooling, fit in kW per kelvin) appear once it is active. *Deutsch:* Wetterkarte zeigt nur \"lernt noch\", bis sie etwas aussagen kann.\n"
     "- **Dashboard cleaned up, graphics first** (user feedback): fewer cards;"),
])
print("ok")
