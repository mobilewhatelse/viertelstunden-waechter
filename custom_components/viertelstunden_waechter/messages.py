"""Texts of the log lines and messages in German and English (pure Python, no Home Assistant imports).

The language follows Home Assistant: German for "de...", English for every other language. Lines already in the log
keep the language they were written in.
"""

from __future__ import annotations

from typing import Any

MESSAGES: dict[str, dict[str, str]] = {
    "de": {
        # decisions
        "ahead": "Vorausschauend ({why}): {text}",
        "limit_lost": "Grenze nicht zu halten: Prognose {fc:.1f} kW (Grenze {limit:.1f} kW), alle Hebel ausgeschöpft",
        "sw_off": "{name} aus ({w:.0f} W, {excess:.1f} kW zu viel)",
        "soc_part": ", Ladestand {soc:.0f} %",
        "bat_rel": "{name}: Batterie freigegeben ({excess:.1f} kW zu viel{soc})",
        "set_rel": "{name}: Einstellung geändert ({excess:.1f} kW zu viel)",
        "script_on": "{name}: Notfall-Eingriff ({excess:.1f} kW zu viel)",
        "thr_down": "{name} {cur:g} → {new:g} ({excess:.1f} kW zu viel)",
        "thr_back": "{name} wieder {v:g}",
        "thr_up": "{name} {cur:g} → {new:g} (wieder mehr Luft)",
        "free": "{name} wieder frei",
        "free_a": "{name} wieder frei ({a} A)",
        "wb3_down": "{name} {cur} A -> {new} A (3-phasig, {excess:.1f} kW zu viel)",
        "wb_to1": "{name} auf 1-phasig {a} A ({excess:.1f} kW zu viel), kurze Ladepause durch Phasenwechsel",
        "wb1_down": "{name} 1-phasig {cur} A -> {new} A",
        "wb_back": "{name} wieder {a} A",
        "wb_phase_back": "{name} wieder {opt}",
        "wb_to3": "{name} wieder 3-phasig ({a} A), kurze Ladepause durch Phasenwechsel",
        "wb1_up": "{name} 1-phasig {cur} A -> {new} A (wieder mehr Luft)",
        "wb3_up": "{name} {cur} A -> {new} A (wieder mehr Luft)",
        "sw_on": "{name} wieder an",
        "sw_stays": "{name} bleibt aus (Zeitplan oder inzwischen anders geschaltet)",
        "bat_back": "{name}: wieder wie vorher",
        "script_off": "{name}: Eingriff zurückgenommen",
        "word_soc": "Ladestand",
        "word_guard": "Schutzwert",
        "below_min": "{name}: {what} {v:g} unter dem Mindestwert ({min:g})",
        "max_off": "{name}: höchste Auszeit ({min:.0f} min) erreicht",
        "all_free": "Alles freigegeben: {reason}",
        # confirmation
        "unreachable": "Gerät nicht erreichbar",
        "cur_not": "Strom steht bei {cur:g} A statt {want} A",
        "no_cur": "kein Stromwert",
        "power_despite": "Leistung {kw:.1f} kW trotz {want} A",
        "still_on": "Gerät ist noch an",
        "val_not": "Wert steht bei {cur:g} statt {want:g}",
        "no_val": "kein Wert",
        "rel_not": "Freigabe nicht übernommen",
        "retry": "{name}: keine Reaktion ({problem}), Befehl wird wiederholt",
        "miss": "{name}: Befehl nicht umgesetzt ({problem}). Das Gerät wird {min} min ausgelassen, der nächste Hebel kommt dran",
        # reasons
        "r_missing": "Messwerte fehlen",
        "r_not_needed": "nicht nötig",
        "r_restart": "Neustart",
        "r_mode": "Betriebsart geändert",
        "r_unload": "Integration beendet",
        "r_risk_over": "Risiko vorbei",
        # coordinator
        "why_forecast": "laut Prognose Spitzen bis {high:.1f} kW, typisch {typ:.1f} kW",
        "push_iv": "Eingriff: {text}",
        "push_done": "Eingriff beendet, alles wieder freigegeben. Das habe ich gemacht:",
        "prewarn": "Vorwarnung: Die Viertelstunde läuft auf {fc:.1f} kW zu (Grenze {limit:.1f} kW, Bezug jetzt {now:.1f} kW)",
        "res_hold": "Akku-Reserve: {name} hält die Ladung für das Risiko {start}–{end} (bis {high:.1f} kW)",
        "res_fail": "Akku-Reserve: {name} nicht gesetzt ({err})",
        "res_back_fail": "Akku-Reserve: {name} nicht zurückgestellt ({err})",
        "res_end": "Akku-Reserve beendet ({reason}): {name} wieder wie vorher",
        "res_end_changed": "Akku-Reserve beendet ({reason}): {name} inzwischen anders eingestellt, nichts geändert",
        "plan_pause": "Ladeplan: Laden pausiert (außerhalb der geplanten Zeiten)",
        "plan_go": "Ladeplan: Laden freigegeben",
        "plan_fail": "Ladeplan: Befehl fehlgeschlagen ({err})",
        "error": "Fehler: {what} ({err})",
        "observed": "(beobachtet)",
    },
    "en": {
        "ahead": "Ahead ({why}): {text}",
        "limit_lost": "Limit cannot be held: forecast {fc:.1f} kW (limit {limit:.1f} kW), all levers used",
        "sw_off": "{name} off ({w:.0f} W, {excess:.1f} kW too much)",
        "soc_part": ", charge {soc:.0f} %",
        "bat_rel": "{name}: battery released ({excess:.1f} kW too much{soc})",
        "set_rel": "{name}: setting changed ({excess:.1f} kW too much)",
        "script_on": "{name}: emergency action ({excess:.1f} kW too much)",
        "thr_down": "{name} {cur:g} → {new:g} ({excess:.1f} kW too much)",
        "thr_back": "{name} back to {v:g}",
        "thr_up": "{name} {cur:g} → {new:g} (more room again)",
        "free": "{name} released",
        "free_a": "{name} released ({a} A)",
        "wb3_down": "{name} {cur} A -> {new} A (3-phase, {excess:.1f} kW too much)",
        "wb_to1": "{name} to 1-phase {a} A ({excess:.1f} kW too much), short charging pause for the phase switch",
        "wb1_down": "{name} 1-phase {cur} A -> {new} A",
        "wb_back": "{name} back to {a} A",
        "wb_phase_back": "{name} back to {opt}",
        "wb_to3": "{name} back to 3-phase ({a} A), short charging pause for the phase switch",
        "wb1_up": "{name} 1-phase {cur} A -> {new} A (more room again)",
        "wb3_up": "{name} {cur} A -> {new} A (more room again)",
        "sw_on": "{name} on again",
        "sw_stays": "{name} stays off (schedule, or switched otherwise meanwhile)",
        "bat_back": "{name}: back as before",
        "script_off": "{name}: action taken back",
        "word_soc": "charge",
        "word_guard": "protection value",
        "below_min": "{name}: {what} {v:g} below the minimum ({min:g})",
        "max_off": "{name}: maximum off time ({min:.0f} min) reached",
        "all_free": "Everything released: {reason}",
        "unreachable": "device not reachable",
        "cur_not": "current is {cur:g} A instead of {want} A",
        "no_cur": "no current value",
        "power_despite": "power {kw:.1f} kW despite {want} A",
        "still_on": "device is still on",
        "val_not": "value is {cur:g} instead of {want:g}",
        "no_val": "no value",
        "rel_not": "release not applied",
        "retry": "{name}: no reaction ({problem}), repeating the command",
        "miss": "{name}: command not carried out ({problem}). The device is left alone for {min} min, the next lever is used",
        "r_missing": "readings missing",
        "r_not_needed": "not needed",
        "r_restart": "restart",
        "r_mode": "mode changed",
        "r_unload": "integration stopped",
        "r_risk_over": "risk over",
        "why_forecast": "forecast peaks up to {high:.1f} kW, typically {typ:.1f} kW",
        "push_iv": "Intervention: {text}",
        "push_done": "Intervention over, everything released. What I did:",
        "prewarn": "Early warning: the quarter hour heads for {fc:.1f} kW (limit {limit:.1f} kW, import now {now:.1f} kW)",
        "res_hold": "Battery reserve: {name} keeps its charge for the risk {start}–{end} (up to {high:.1f} kW)",
        "res_fail": "Battery reserve: {name} not set ({err})",
        "res_back_fail": "Battery reserve: {name} not put back ({err})",
        "res_end": "Battery reserve ended ({reason}): {name} back as before",
        "res_end_changed": "Battery reserve ended ({reason}): {name} was changed meanwhile, nothing done",
        "plan_pause": "Charge plan: charging paused (outside the planned times)",
        "plan_go": "Charge plan: charging allowed",
        "plan_fail": "Charge plan: command failed ({err})",
        "error": "Error: {what} ({err})",
        "observed": "(observed)",
    },
}


def language(lang: str | None) -> str:
    """'de' for German Home Assistant installations, 'en' for all others."""
    return "de" if str(lang or "").lower().startswith("de") else "en"


class Messages:
    def __init__(self, lang: str | None = "de") -> None:
        self.lang = language(lang)

    def __call__(self, key: str, **values: Any) -> str:
        return MESSAGES[self.lang][key].format(**values)
