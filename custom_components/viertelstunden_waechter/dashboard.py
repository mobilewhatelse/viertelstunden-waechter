"""Builds a ready-made dashboard for the guard (pure Python, no Home Assistant imports).

`build_views(ids, lang)` gets the entity ids of this installation (key -> entity id, resolved through the entity
registry, so they are right whatever the language or the name of the device) and returns Lovelace views.
Only standard cards are used (entities, tile, markdown, statistics-graph): no custom card needs to be installed.
"""

from __future__ import annotations

from typing import Any

try:
    from . import dashboard_charts as charts
except ImportError:  # imported as a plain module (tests)
    import dashboard_charts as charts

TEXTS: dict[str, dict[str, str]] = {
    "de": {
        "view_main": "Wächter", "view_stats": "Statistik und Prognose",
        "intro": "**Nur beobachten** = der Wächter entscheidet und schreibt mit, schaltet aber nichts. „Aktiv“ ist gesperrt, solange die Sperre aus den allgemeinen Einstellungen an ist.",
        "settings": "Einstellungen", "features": "Zusatzfunktionen und Preise",
        "now": "Jetzt", "costs": "Kosten und Ersparnis", "forecast": "Prognose 24 Stunden",
        "profile": "Typisches Wochenprofil", "peaks": "Spitzen", "months": "Monate", "interventions": "Eingriffe je Tag",
        "mode": "Betriebsart", "strategy": "Strategie", "limit": "Grenze (kW)", "margin": "Sicherheitsabstand (kW)",
        "paid_peak": "Bereits erreichte Spitze nutzen", "notify": "Meldung bei Eingriff", "costs_on": "Kosten und Ersparnis berechnen",
        "forecast_on": "Lastprognose lernen und anzeigen", "price_low": "Leistungspreis bis zur Schwelle (pro kW und Jahr)",
        "price_high": "Leistungspreis über der Schwelle (pro kW und Jahr)", "threshold": "Preisschwelle (kW)",
        "status": "Status", "prognosis": "Prognose Viertelstunde", "allowed": "Erlaubt jetzt", "so_far": "Viertelstunde bisher",
        "last": "Letzte Viertelstunde", "peak_today": "Spitze heute", "peak_month": "Spitze im Monat", "iv_today": "Eingriffe heute",
        "cost_month": "Leistungspreis diesen Monat", "cost_without": "Ohne Wächter (Schätzung)", "saving_month": "Ersparnis Monat",
        "saving_year": "Ersparnis Jahr", "saved_now": "Entlastung jetzt",
        "typical_now": "Typisch jetzt", "expected_peak": "Erwartete Spitze 24 h", "next_risk": "Nächstes Risiko",
        "risk_none": "keines in den nächsten 24 Stunden", "risk_today": "heute", "risk_up_to": "bis",
        "reserve_on": "Akku-Reserve vor einer Spitze (Standard aus)", "ai_on": "KI-Erklärer (Standard aus, nach Neustart aus)",
        "ai_title": "Erklärung des Tages", "ai_none": "Noch keine Erklärung. Der Erklärer schreibt abends um 21 Uhr, wenn er eingeschaltet und in den Einstellungen eine KI-Aufgabe gewählt ist.",
        "expl_from": "Erklärung vom", "expl_next": "Die Erklärung für heute kommt abends um 21 Uhr.", "expl_error": "Die Erklärung konnte nicht erstellt werden",
        "predictive": "Vorausschauend drosseln nach Prognose (Standard aus)", "prewarn": "Vorwarnung vor Eingriff (Standard aus)", "weekly_on": "Wochenbericht (montags)", "weekly": "Letzter Wochenbericht",
        "no_report": "Noch kein Wochenbericht (der erste kommt am Montag, sobald Daten einer Woche da sind).",
        "view_today": "Heute", "now_title": "Jetzt", "now_of": "Prognose dieser Viertelstunde / Ziel", "legend_now": "Weißer Strich = Ziel, roter gestrichelter Strich = Grenze. Grün = sicher darunter, gelb = knapp, rot = über der Grenze.", "quarters_title": "Die Viertelstunden von heute", "legend_quarters": "Jeder Balken eine abgeschlossene Viertelstunde, rot = über der Grenze.", "last_iv": "Letzte Eingriffe", "no_iv_today": "Heute noch keine Eingriffe.", "mode_title": "Betriebsart",
        "today": "Heute", "no_decisions": "Noch keine Entscheidungen heute.", "devices": "Geräte und Prioritäten",
        "measure": "Messung", "grid": "Netzbezug", "counter": "Bezugszähler", "lock": "Sperre „Aktiv“",
        "prio": "Prio", "device": "Gerät", "action": "Eingriff", "controls": "Steuert",
        "change": "Ändern: Konfigurieren", "loading": "Der Wächter lädt noch (oder ist nicht eingerichtet).",
        "estimate": "Die Ersparnis ist eine **Schätzung** und wird nur in der Betriebsart **Aktiv** gezählt.",
        "peak_label": "Erwartete Spitze", "target": "Ziel", "no_forecast": "Noch keine Prognose.",
        "profile_help": "Je Wochentag 24 Stunden (0–23 Uhr), höher = mehr Netzbezug. Oben: typisch, unten: höchste Werte.",
        "typical": "typisch", "highest": "höchste", "days": "Mo,Di,Mi,Do,Fr,Sa,So",
        "col_day": "Tag", "col_peak": "höchste ¼ h", "col_at": "um", "col_month": "Monat", "col_without": "ohne Wächter",
        "col_cost": "Kosten", "col_saving": "Ersparnis", "col_real": "echt", "col_observed": "beobachtet",
        "chart_peaks": "Höchste Viertelstunde je Stunde, letzte 3 Tage (kW)", "windows": "Risikofenster", "none": "keine",
        "daily": "Höchste Viertelstunde je Tag, letzte 6 Wochen", "months_chart": "Spitze je Monat",
        "legend_forecast": "Voller Balken = typischer Bezug, heller Balken = höchster erwarteter Wert, rot = über dem Ziel.",
        "legend_profile": "Je Wochentag und Stunde (0–23 Uhr): Farbe von dunkelblau über türkis, grün und gelb bis orange = mehr Netzbezug (jedes Feld auf seinen eigenen Höchstwert skaliert), rot = über dem Ziel.",
        "legend_daily": "Jeder Balken ein Tag, rot = über der Grenze. Werte aus dem importierten Verlauf sind Stundenmittel (Untergrenze).",
        "legend_months": "Voller Balken = Spitze des Monats, gestrichelt = Schätzung ohne Wächter.",
        "hour_label": "Typisch|Höchste Werte|Uhr (0–23)", "limit_label": "Grenze", "target_label": "Ziel",
        "weeks": "Tagesspitzen der letzten 10 Wochen", "day_letters": "MDMDFSS",
        "weeks_help": "Eine Zeile je Woche (Mo–So), höher = höhere Spitze, ▲ = über der Grenze, · = keine Daten.",
        "enough_data": "Die Tabelle füllt sich mit jeder Viertelstunde.",
        "when_on": "aus ab", "wallbox": "dann 1-phasig", "script": "Skript", "battery": "Batterie ab",
        "setting": "Einstellung ändern", "throttle": "Schritt", "if_only": "eingreifen nur, wenn", "again_only": "wieder an nur, wenn",
        "plan": "Ladeplan fürs Auto", "plan_on": "Ladeplan berechnen", "plan_exec": "Ladeplan auch ausführen (Standard aus)",
        "plan_status": "Ladeplan", "ready": "Fertig ca.", "departure": "Abfahrt", "soc": "Ladestand", "missing": "Es fehlen", "vehicle_hint": "Ohne Fahrzeug-Eintrag (Konfigurieren) gibt es keinen Plan.",
        "paused_by_plan": "Der Plan hat das Laden pausiert.", "executing": "Der Plan wird ausgeführt.",
    },
    "en": {
        "view_main": "Guard", "view_stats": "Statistics and forecast",
        "intro": "**Observe only** = the guard decides and logs but switches nothing. \"Active\" is refused while the lock from the general settings is on.",
        "settings": "Settings", "features": "Features and prices",
        "now": "Now", "costs": "Cost and savings", "forecast": "24-hour forecast",
        "profile": "Typical weekly profile", "peaks": "Peaks", "months": "Months", "interventions": "Interventions per day",
        "mode": "Mode", "strategy": "Strategy", "limit": "Limit (kW)", "margin": "Safety margin (kW)",
        "paid_peak": "Use peak already reached", "notify": "Message on intervention", "costs_on": "Calculate cost and savings",
        "forecast_on": "Learn and show the load forecast", "price_low": "Demand charge up to the threshold (per kW and year)",
        "price_high": "Demand charge above the threshold (per kW and year)", "threshold": "Price threshold (kW)",
        "status": "Status", "prognosis": "Quarter-hour forecast", "allowed": "Allowed now", "so_far": "Quarter hour so far",
        "last": "Last quarter hour", "peak_today": "Peak today", "peak_month": "Peak this month", "iv_today": "Interventions today",
        "cost_month": "Demand charge this month", "cost_without": "Without the guard (estimate)", "saving_month": "Savings this month",
        "saving_year": "Savings this year", "saved_now": "Relief now",
        "typical_now": "Typical now", "expected_peak": "Expected peak in 24 h", "next_risk": "Next risk",
        "risk_none": "none in the next 24 hours", "risk_today": "today", "risk_up_to": "up to",
        "reserve_on": "Battery reserve before a peak (default off)", "ai_on": "AI explainer (default off, off after restart)",
        "ai_title": "Explanation of the day", "ai_none": "No explanation yet. The explainer writes at 21:00 when it is switched on and an AI task is chosen in the settings.",
        "expl_from": "Explanation of", "expl_next": "The explanation for today follows in the evening at 21:00.", "expl_error": "The explanation could not be created",
        "predictive": "Throttle ahead using the forecast (default off)", "prewarn": "Early warning before an intervention (default off)", "weekly_on": "Weekly report (Mondays)", "weekly": "Last weekly report",
        "no_report": "No weekly report yet (the first comes on Monday once a week of data exists).",
        "view_today": "Today", "now_title": "Now", "now_of": "Forecast of this quarter hour / target", "legend_now": "White mark = target, red dashed mark = limit. Green = safely below, yellow = close, red = above the limit.", "quarters_title": "Today's quarter hours", "legend_quarters": "Each bar one finished quarter hour, red = above the limit.", "last_iv": "Latest interventions", "no_iv_today": "No interventions yet today.", "mode_title": "Mode",
        "today": "Today", "no_decisions": "No decisions yet today.", "devices": "Devices and priorities",
        "measure": "Measurement", "grid": "Grid import", "counter": "Import counter", "lock": "Lock for \"Active\"",
        "prio": "Prio", "device": "Device", "action": "Action", "controls": "Controls",
        "change": "Change: Configure", "loading": "The guard is still loading (or not set up).",
        "estimate": "Savings are an **estimate** and are only counted in the mode **Active**.",
        "peak_label": "Expected peak", "target": "Target", "no_forecast": "No forecast yet.",
        "profile_help": "Per weekday 24 hours (0-23 h), higher = more grid import. Top: typical, bottom: highest values.",
        "typical": "typical", "highest": "highest", "days": "Mon,Tue,Wed,Thu,Fri,Sat,Sun",
        "col_day": "Day", "col_peak": "highest ¼ h", "col_at": "at", "col_month": "Month", "col_without": "without guard",
        "col_cost": "Cost", "col_saving": "Savings", "col_real": "real", "col_observed": "observed",
        "chart_peaks": "Highest quarter hour per hour, last 3 days (kW)", "windows": "Risk windows", "none": "none",
        "daily": "Highest quarter hour per day, last 6 weeks", "months_chart": "Peak per month",
        "legend_forecast": "Solid bar = typical import, light bar = highest expected value, red = above the target.",
        "legend_profile": "Per weekday and hour (0-23 h): colour from dark blue via teal, green and yellow to orange = more grid import (each panel scaled to its own maximum), red = above the target.",
        "legend_daily": "Each bar one day, red = above the limit. Values from imported history are hourly means (lower bound).",
        "legend_months": "Solid bar = peak of the month, dashed = estimate without the guard.",
        "hour_label": "Typical|Highest values|Hour (0-23)", "limit_label": "Limit", "target_label": "Target",
        "weeks": "Daily peaks of the last 10 weeks", "day_letters": "MTWTFSS",
        "weeks_help": "One line per week (Mon-Sun), higher = higher peak, ▲ = above the limit, · = no data.",
        "enough_data": "The table fills with every quarter hour.",
        "when_on": "off from", "wallbox": "then 1 phase", "script": "script", "battery": "battery from",
        "setting": "change setting", "throttle": "step", "if_only": "intervene only if", "again_only": "on again only if",
        "plan": "Charge plan for the car", "plan_on": "Calculate the charge plan", "plan_exec": "Also carry out the plan (default off)",
        "plan_status": "Charge plan", "ready": "Ready about", "departure": "Departure", "soc": "State of charge", "missing": "Missing", "vehicle_hint": "Without a vehicle entry (Configure) there is no plan.",
        "paused_by_plan": "The plan has paused the charging.", "executing": "The plan is being carried out.",
    },
}


def _t(lang: str) -> dict[str, str]:
    return TEXTS["de" if lang.startswith("de") else "en"]


def _config_markdown(ids: dict[str, str], x: dict[str, str]) -> str:
    s = ids["status"]
    return (
        "{% set c = state_attr('" + s + "', 'configuration') %}"
        "{% macro n(e) %}{% set st = states[e] if e else none %}{{ st.name if st else (e or '–') }}{% endmacro %}"
        "{% if c %}**" + x["measure"] + "**\n"
        "- " + x["grid"] + ": {{ n(c.get('grid_power')) }}\n"
        "- " + x["counter"] + ": {{ n(c.get('grid_energy')) }}{% if c.get('lock') %}\n"
        "- " + x["lock"] + ": {{ n(c.get('lock')) }}{% endif %}\n\n"
        "| " + x["prio"] + " | " + x["device"] + " | " + x["action"] + " | " + x["controls"] + " |\n"
        "|---:|---|---|---|\n"
        "{% for d in c.get('devices', []) %}| {{ d.get('priority') }} | {{ d.get('name') }} | "
        "{% set k = d.get('kind') %}"
        "{% if k == 'wallbox' %}{{ d.get('max_current') }}→{{ d.get('min_current') }} A{{ ', " + x["wallbox"] + "' if d.get('one_phase_option') else '' }}"
        "{% elif k == 'switch' %}" + x["when_on"] + " {{ d.get('min_power_w') | int(0) }} W"
        "{% elif k == 'battery' %}" + x["battery"] + " {{ d.get('min_soc') | int(0) }} %"
        "{% elif k == 'vehicle' %}" + x["plan"] + ""
        "{% elif k == 'setting' %}" + x["setting"] + ""
        "{% elif k == 'throttle' %}{{ d.get('max_value') }}→{{ d.get('min_value') }}, " + x["throttle"] + " {{ d.get('step') }}"
        "{% else %}" + x["script"] + "{% endif %} | "
        "{{ n(d.get('current_entity') or d.get('switch_entity') or d.get('value_entity') or d.get('release_entity_1') or d.get('on_script')) }} |\n"
        "{% endfor %}\n"
        "{% for d in c.get('devices', []) if d.get('allow_entity') or d.get('restore_entity') %}- {{ d.get('name') }}:"
        "{% if d.get('allow_entity') %} " + x["if_only"] + " „{{ n(d.get('allow_entity')) }}“{% endif %}"
        "{% if d.get('restore_entity') %} " + x["again_only"] + " „{{ n(d.get('restore_entity')) }}“{% endif %}\n"
        "{% endfor %}\n"
        "[" + x["change"] + "](/config/integrations/integration/viertelstunden_waechter)"
        "{% else %}" + x["loading"] + "{% endif %}"
    )


def _explanation_markdown(ids: dict[str, str], x: dict[str, str]) -> str:
    """The explanation of the day with its date: an old explanation is labelled and never shown as today's."""
    s = ids["ai_explanation"]
    return (
        "{% set s = '" + s + "' %}{% set r = state_attr(s, 'text') %}{% set d = states(s) %}"
        "{% if r %}{% if d == now().strftime('%Y-%m-%d') %}{{ r }}"
        "{% else %}*" + x["expl_from"] + " {{ d[8:10] }}.{{ d[5:7] }}.:* {{ r }}\n\n" + x["expl_next"] + "{% endif %}"
        "{% elif state_attr(s, 'error') %}\u26a0\ufe0f " + x["expl_error"] + ": {{ state_attr(s, 'error') }}"
        "{% else %}" + x["ai_none"] + "{% endif %}"
    )


def _recent_markdown(ids: dict[str, str], x: dict[str, str]) -> str:
    """The latest lines of today's log (phone view)."""
    s = ids["status"]
    return (
        "{% set s = '" + s + "' %}{% set z = (state_attr(s, 'today') or [])[:6] %}"
        "{% for l in z %}- {{ l }}\n{% else %}" + x["no_iv_today"] + "{% endfor %}"
    )


def _today_markdown(ids: dict[str, str], x: dict[str, str]) -> str:
    s = ids["status"]
    return (
        "{% set s = '" + s + "' %}{% set e = state_attr(s, 'interventions') or [] %}"
        "**{{ state_translated(s) }}**{% if e %} · {{ e | join(', ') }}{% endif %}\n\n"
        "**" + x["today"] + "**\n"
        "{% for z in state_attr(s, 'today') or [] %}\n- {{ z }}\n{% else %}\n" + x["no_decisions"] + "\n{% endfor %}"
    )


def _forecast_markdown(ids: dict[str, str], x: dict[str, str]) -> str:
    s = ids["forecast_peak"]
    return (
        "{% set s = '" + s + "' %}{% set hours = state_attr(s, 'hours') or [] %}"
        "{% set target = state_attr(s, 'target_kw') | float(10) %}"
        "{% if hours %}**" + x["peak_label"] + ":** {{ states(s) }} kW · " + x["target"] + " {{ target }} kW\n\n"
        "{% set w = state_attr(s, 'windows') or [] %}**" + x["windows"] + ":** "
        "{% for a in w %}{{ a.get('start')[11:16] }}–{{ a.get('end')[11:16] }} ({{ '%.1f' | format(a.get('high_kw')) }} kW){{ ', ' if not loop.last }}"
        "{% else %}" + x["none"] + "{% endfor %}"
        "{% else %}" + x["no_forecast"] + "{% endif %}"
    )


def _profile_markdown(ids: dict[str, str], x: dict[str, str]) -> str:
    s = ids["forecast_now"]
    days = x["days"]
    return (
        "{% set prof = state_attr('" + s + "', 'profile') or [] %}{% set blocks = '▁▂▃▄▅▆▇█' %}"
        "{% set names = '" + days + "'.split(',') %}"
        "{% set ns = namespace(vmax=1.0) %}"
        "{% for d in prof %}{% for v in d.get('high') %}{% if v is not none and v > ns.vmax %}{% set ns.vmax = v %}{% endif %}{% endfor %}{% endfor %}"
        "{% if prof %}" + x["profile_help"] + " (max. {{ '%.1f' | format(ns.vmax) }} kW)\n\n```\n"
        "     ┬·····┬·····┬·····┬·····  0-6-12-18 h\n"
        "{% for d in prof %}{{ names[d.get('day')] }} {% for v in d.get('typical') %}{{ '·' if v is none else blocks[((v / ns.vmax) * 7) | round(0) | int] }}{% endfor %}  " + x["typical"] + "\n"
        "   {% for v in d.get('high') %}{{ '·' if v is none else blocks[((v / ns.vmax) * 7) | round(0) | int] }}{% endfor %}  " + x["highest"] + "\n{% endfor %}```\n"
        "{% else %}" + x["no_forecast"] + "{% endif %}"
    )


def _peaks_markdown(ids: dict[str, str], x: dict[str, str]) -> str:
    s = ids["today_peak"]
    return (
        "{% set d = state_attr('" + s + "', 'days') or [] %}{% set g = states('" + ids["limit"] + "') | float(10) %}"
        "{% if d %}| " + x["col_day"] + " | " + x["col_peak"] + " | " + x["col_at"] + " |\n|---|---:|---|\n"
        "{% for r in d[:14] %}| {{ r.get('date')[8:10] }}.{{ r.get('date')[5:7] }}. | {{ '%.2f' | format(r.get('kw')) }} kW"
        "{{ ' ⚠️' if r.get('kw') > g else '' }} | {{ r.get('at') }} |\n{% endfor %}{% else %}" + x["enough_data"] + "{% endif %}"
    )


def _weeks_markdown(ids: dict[str, str], x: dict[str, str]) -> str:
    s = ids["today_peak"]
    return (
        "{% set peaks = state_attr('" + s + "', 'peaks_by_day') or {} %}{% set g = states('" + ids["limit"] + "') | float(10) %}"
        "{% set blocks = '▁▂▃▄▅▆▇█' %}{% set ns = namespace(vmax=g) %}"
        "{% for k, v in peaks.items() %}{% if v > ns.vmax %}{% set ns.vmax = v %}{% endif %}{% endfor %}"
        "{% set today = now().date() %}{% set monday = today - timedelta(days=today.weekday()) %}"
        "{% if peaks %}" + x["weeks_help"] + " (max. {{ '%.1f' | format(ns.vmax) }} kW, {{ '%.1f' | format(g) }} kW)\n\n```\n"
        "       " + x["day_letters"] + "\n"
        "{% for w in range(9, -1, -1) %}{% set ws = monday - timedelta(weeks=w) %}{{ ws.strftime('%d.%m.') }} "
        "{% for d in range(7) %}{% set day = ws + timedelta(days=d) %}{% set v = peaks.get(day.strftime('%Y-%m-%d')) %}"
        "{{ '·' if v is none or day > today else ('▲' if v > g else blocks[((v / ns.vmax) * 7) | round(0) | int]) }}{% endfor %}\n{% endfor %}```\n"
        "{% else %}" + x["enough_data"] + "{% endif %}"
    )


def _next_risk_markdown(ids: dict[str, str], x: dict[str, str]) -> str:
    """The next risk window as text; the sensor has no value (shown as unknown) when there is none."""
    s = ids["next_risk"]
    return (
        "{% set s = '" + s + "' %}{% set st = states(s) %}{% set names = '" + x["days"] + "'.split(',') %}"
        "{% if st not in ['unknown', 'unavailable', 'none', ''] and state_attr(s, 'until') %}"
        "{% set a = as_datetime(st) | as_local %}{% set e = as_datetime(state_attr(s, 'until')) | as_local %}"
        "**" + x["next_risk"] + ":** {{ '" + x["risk_today"] + "' if a.date() == now().date() else names[a.weekday()] }} "
        "{{ a.strftime('%H:%M') }}–{{ e.strftime('%H:%M') }}, " + x["risk_up_to"] + " "
        "{{ '%.1f' | format(state_attr(s, 'high_kw') | float(0)) }} kW"
        "{% else %}**" + x["next_risk"] + ":** " + x["risk_none"] + "{% endif %}"
    )


def _months_markdown(ids: dict[str, str], x: dict[str, str]) -> str:
    s = ids["month_peak"]
    return (
        "{% set m = state_attr('" + s + "', 'months') or [] %}"
        "{% if m %}| " + x["col_month"] + " | " + x["col_peak"] + " | " + x["col_without"] + " | " + x["col_cost"] + " | " + x["col_saving"] + " |\n"
        "|---|---:|---:|---:|---:|\n"
        "{% for r in m | reverse %}| {{ r.get('month') }} | {{ '%.2f' | format(r.get('peak_kw') or 0) }} kW | "
        "{{ '%.2f' | format(r.get('peak_without_kw') or 0) }} kW | "
        "{{ '%.2f' | format(r.get('cost')) if r.get('cost') is not none else '–' }} | "
        "{{ '%.2f' | format(r.get('saving')) if r.get('saving') is not none else '–' }} |\n{% endfor %}"
        "{% else %}" + x["enough_data"] + "{% endif %}"
    )


def _interventions_markdown(ids: dict[str, str], x: dict[str, str]) -> str:
    s = ids["interventions_today"]
    return (
        "{% set d = state_attr('" + s + "', 'days') or [] %}"
        "{% if d %}| " + x["col_day"] + " | " + x["col_real"] + " | " + x["col_observed"] + " |\n|---|---:|---:|\n"
        "{% for r in d %}| {{ r.get('date')[8:10] }}.{{ r.get('date')[5:7] }}. | {{ r.get('real') }} | {{ r.get('observed') }} |\n{% endfor %}"
        "{% else %}" + x["no_decisions"] + "{% endif %}"
    )


def _plan_markdown(ids: dict[str, str], x: dict[str, str]) -> str:
    s = ids["charge_plan"]
    return (
        "{% set s = '" + s + "' %}{% set st = states(s) %}**{{ state_translated(s) }}**\n\n"
        "{% if st == 'no_vehicle' %}" + x["vehicle_hint"] + "{% endif %}"
        "{% if st in ['planned', 'infeasible', 'not_needed'] %}"
        "{% set ra = state_attr(s, 'ready_at') %}{% set dp = state_attr(s, 'departure') %}"
        "" + x["soc"] + " {{ state_attr(s, 'soc') | int(0) }} → {{ state_attr(s, 'target_soc') | int(0) }} %"
        "{% if dp %} · " + x["departure"] + " {{ dp[11:16] }}{% endif %}{% if ra %} · " + x["ready"] + " {{ ra[11:16] }}{% endif %}\n"
        "{% for z in state_attr(s, 'text') or [] %}\n- {{ z }}{% endfor %}\n"
        "{% if (state_attr(s, 'shortfall_kwh') or 0) > 0.1 %}\n⚠ " + x["missing"] + " {{ '%.1f' | format(state_attr(s, 'shortfall_kwh')) }} kWh{% endif %}"
        "{% if state_attr(s, 'paused_by_plan') %}\n\n" + x["paused_by_plan"] + "{% elif state_attr(s, 'executing') %}\n\n" + x["executing"] + "{% endif %}"
        "{% if state_attr(s, 'hint') %}\n\n*{{ state_attr(s, 'hint') }}*{% endif %}"
        "{% endif %}"
    )


def _tile(entity: str, name: str) -> dict[str, Any]:
    return {"type": "tile", "entity": entity, "name": name}


def build_views(ids: dict[str, str], lang: str = "en") -> list[dict[str, Any]]:
    """Three views: the daily overview, the compact view for the phone ("today") and statistics with forecast."""
    x = _t(lang)
    main = {
        "title": x["view_main"], "path": "waechter", "type": "sections", "max_columns": 3,
        "sections": [
            {"type": "grid", "cards": [
                {"type": "heading", "heading": x["view_main"], "icon": "mdi:shield-half-full"},
                {"type": "markdown", "content": x["intro"]},
                {"type": "entities", "title": x["settings"], "entities": [
                    {"entity": ids["mode"], "name": x["mode"]}, {"entity": ids["strategy"], "name": x["strategy"]},
                    {"entity": ids["limit"], "name": x["limit"]}, {"entity": ids["margin"], "name": x["margin"]}]},
                {"type": "entities", "title": x["features"], "entities": [
                    {"entity": ids["paid_peak"], "name": x["paid_peak"]}, {"entity": ids["notify_intervention"], "name": x["notify"]},
                    {"entity": ids["costs_enabled"], "name": x["costs_on"]}, {"entity": ids["forecast_enabled"], "name": x["forecast_on"]},
                    {"entity": ids["predictive"], "name": x["predictive"]}, {"entity": ids["battery_reserve"], "name": x["reserve_on"]},
                    {"entity": ids["ai_explainer"], "name": x["ai_on"]}, {"entity": ids["prewarn"], "name": x["prewarn"]}, {"entity": ids["weekly_report_enabled"], "name": x["weekly_on"]},
                    {"entity": ids["price_low"], "name": x["price_low"]}, {"entity": ids["price_high"], "name": x["price_high"]},
                    {"entity": ids["price_threshold"], "name": x["threshold"]}]},
                {"type": "markdown", "title": x["devices"], "content": _config_markdown(ids, x)},
            ]},
            {"type": "grid", "cards": [
                {"type": "heading", "heading": x["now"], "icon": "mdi:timer-outline"},
                _tile(ids["status"], x["status"]), _tile(ids["forecast"], x["prognosis"]), _tile(ids["allowed"], x["allowed"]),
                _tile(ids["quarter_energy"], x["so_far"]), _tile(ids["last_quarter"], x["last"]),
                _tile(ids["today_peak"], x["peak_today"]), _tile(ids["month_peak"], x["peak_month"]),
                _tile(ids["interventions_today"], x["iv_today"]),
                {"type": "markdown", "content": _today_markdown(ids, x)},
            ]},
            {"type": "grid", "cards": [
                {"type": "heading", "heading": x["costs"], "icon": "mdi:currency-eur"},
                _tile(ids["cost_month"], x["cost_month"]), _tile(ids["cost_without"], x["cost_without"]),
                _tile(ids["savings_month"], x["saving_month"]), _tile(ids["savings_year"], x["saving_year"]),
                _tile(ids["saved_now"], x["saved_now"]),
                {"type": "markdown", "content": x["estimate"]},
            ]},
        ],
    }
    today = {
        "title": x["view_today"], "path": "heute", "type": "sections", "max_columns": 1,
        "sections": [
            {"type": "grid", "cards": [
                {"type": "heading", "heading": x["now_title"], "icon": "mdi:shield-half-full"},
                _tile(ids["status"], x["status"]),
                {"type": "markdown", "content": charts.now_bar(ids, x["now_of"], x["legend_now"])},
                {"type": "entities", "entities": [{"entity": ids["mode"], "name": x["mode_title"]}]},
                _tile(ids["today_peak"], x["peak_today"]), _tile(ids["month_peak"], x["peak_month"]),
                _tile(ids["interventions_today"], x["iv_today"]),
            ]},
            {"type": "grid", "cards": [
                {"type": "heading", "heading": x["quarters_title"], "icon": "mdi:chart-bar"},
                {"type": "markdown", "content": charts.today_quarters(ids, x["limit_label"], x["legend_quarters"], x["enough_data"])},
                {"type": "heading", "heading": x["last_iv"], "icon": "mdi:counter"},
                {"type": "markdown", "content": _recent_markdown(ids, x)},
                {"type": "heading", "heading": x["ai_title"], "icon": "mdi:robot-outline"},
                {"type": "markdown", "content": _explanation_markdown(ids, x)},
            ]},
        ],
    }
    stats = {
        "title": x["view_stats"], "path": "statistik", "type": "sections", "max_columns": 3,
        "sections": [
            {"type": "grid", "cards": [
                {"type": "heading", "heading": x["forecast"], "icon": "mdi:chart-timeline-variant"},
                _tile(ids["forecast_now"], x["typical_now"]), _tile(ids["forecast_peak"], x["expected_peak"]),
                {"type": "markdown", "content": _next_risk_markdown(ids, x)},
                {"type": "markdown", "content": _forecast_markdown(ids, x)},
                {"type": "markdown", "content": charts.forecast(ids, x["target_label"], x["legend_forecast"], x["no_forecast"])},
            ]},
            {"type": "grid", "cards": [
                {"type": "heading", "heading": x["plan"], "icon": "mdi:ev-station"},
                _tile(ids["charge_plan"], x["plan_status"]),
                {"type": "entities", "entities": [
                    {"entity": ids["charge_plan_enabled"], "name": x["plan_on"]},
                    {"entity": ids["charge_plan_execute"], "name": x["plan_exec"]}]},
                {"type": "markdown", "content": _plan_markdown(ids, x)},
            ]},
            {"type": "grid", "cards": [
                {"type": "heading", "heading": x["profile"], "icon": "mdi:calendar-week"},
                {"type": "markdown", "content": charts.profile(ids, x["days"], x["hour_label"], x["legend_profile"], x["no_forecast"])},
            ]},
            {"type": "grid", "cards": [
                {"type": "heading", "heading": x["peaks"], "icon": "mdi:calendar-month"},
                {"type": "markdown", "content": _peaks_markdown(ids, x)},
                {"type": "heading", "heading": x["daily"], "icon": "mdi:chart-bar"},
                {"type": "markdown", "content": charts.daily(ids, x["limit_label"], x["legend_daily"], x["enough_data"])},
                {"type": "statistics-graph", "title": x["chart_peaks"], "entities": [ids["last_quarter"]],
                 "stat_types": ["max"], "period": "hour", "days_to_show": 3, "chart_type": "bar"},
            ]},
            {"type": "grid", "cards": [
                {"type": "heading", "heading": x["months"], "icon": "mdi:calendar-range"},
                {"type": "markdown", "content": charts.months(ids, x["limit_label"], x["legend_months"], x["enough_data"])},
                {"type": "markdown", "content": _months_markdown(ids, x)},
                {"type": "heading", "heading": x["interventions"], "icon": "mdi:counter"},
                {"type": "markdown", "content": _interventions_markdown(ids, x)},
                {"type": "heading", "heading": x["ai_title"], "icon": "mdi:robot-outline"},
                {"type": "markdown", "content": _explanation_markdown(ids, x)},
                {"type": "heading", "heading": x["weekly"], "icon": "mdi:calendar-week"},
                {"type": "markdown", "content": "{% set r = state_attr('" + ids["weekly_report"] + "', 'text') %}{{ (r | replace('\n', '  \n')) if r else '" + x["no_report"] + "' }}"},
            ]},
        ],
    }
    return [main, today, stats]


ENTITY_KEYS: dict[str, str] = {
    "mode": "select", "strategy": "select",
    "limit": "number", "margin": "number", "price_low": "number", "price_high": "number", "price_threshold": "number",
    "paid_peak": "switch", "notify_intervention": "switch", "prewarn": "switch", "predictive": "switch", "battery_reserve": "switch", "ai_explainer": "switch", "ai_explanation": "sensor", "weekly_report_enabled": "switch", "weekly_report": "sensor", "costs_enabled": "switch", "forecast_enabled": "switch",
    "status": "sensor", "forecast": "sensor", "allowed": "sensor", "quarter_energy": "sensor", "last_quarter": "sensor",
    "today_peak": "sensor", "month_peak": "sensor", "interventions_today": "sensor", "cost_month": "sensor",
    "cost_without": "sensor", "savings_month": "sensor", "savings_year": "sensor", "saved_now": "sensor",
    "forecast_now": "sensor", "forecast_peak": "sensor", "next_risk": "sensor",
    "charge_plan": "sensor", "charge_plan_enabled": "switch", "charge_plan_execute": "switch",
}
