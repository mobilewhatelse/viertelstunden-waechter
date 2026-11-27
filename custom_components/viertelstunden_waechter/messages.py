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
        "watch": "Nur beobachten: {name} würde um {kw:.1f} kW gesenkt ({excess:.1f} kW zu viel), es wurde nichts gesendet (beim Gerät ist „Nur beobachten“ an)",
        "corrected": "Viertelstunde {start} korrigiert: {old:.2f} kW -> {new:.2f} kW (Wert vom Zähler)",
        "removed": "Viertelstunde {start} aus der Aufzeichnung genommen: {old:.2f} kW war kein Messwert",
        "watch_wb": "Nur beobachten: {name} würde von {cur} A auf {new} A begrenzt (−{kw:.1f} kW, {excess:.1f} kW zu viel), es wurde nichts gesendet (beim Gerät ist „Nur beobachten“ an)",
        "watch_wb1": "Nur beobachten: {name} würde auf 1 Phase mit {new} A umgeschaltet ({excess:.1f} kW zu viel), es wurde nichts gesendet (beim Gerät ist „Nur beobachten“ an)",
        "wb_twice": "Wallbox {a} und evcc-Ladepunkt {b} laden gleichzeitig mit fast gleicher Leistung ({kw:.1f} kW). Ist das dieselbe Wallbox? Bitte nur einmal eintragen.",
        "grid_differ": "Netzbezug: Ihr Sensor zeigt {a:.1f} kW, evcc zeigt {b:.1f} kW. Der Wächter regelt mit Ihrem Sensor.",
        "grid_backup_on": "Netzbezug: Ihr Sensor liefert nichts Brauchbares, der Wächter nimmt vorübergehend den Wert von evcc ({b:.1f} kW).",
        "grid_backup_off": "Netzbezug: Ihr Sensor liefert wieder, der Wächter regelt wieder damit.",
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
        "wb2_down": "{name} {cur} A -> {new} A (2-phasig, {excess:.1f} kW zu viel)",
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
        # precautionary lock (0.15.1)
        "pc_lock": "Vorsorgliche Sperre: {name} gesperrt (Spielraum {room:.1f} kW, Anlauf {kw:.1f} kW)",
        "pc_would_lock": "Vorsorgliche Sperre: {name} hätte vorsorglich gesperrt (Spielraum {room:.1f} kW, Anlauf {kw:.1f} kW), es wurde nichts gesendet",
        "pc_free": "Vorsorgliche Sperre: {name} freigegeben (Spielraum {room:.1f} kW)",
        "pc_would_free": "Vorsorgliche Sperre: {name} hätte wieder freigegeben (Spielraum {room:.1f} kW)",
        "pc_max": "Vorsorgliche Sperre: {name} nach der Höchstdauer ({min:.0f} min) freigegeben, die nächste vorsorgliche Sperre frühestens in {min:.0f} min",
        "pc_running": "Vorsorgliche Sperre: {name} läuft trotz Sperre, Sperre zurückgenommen (die normale Regelung übernimmt)",
        "pc_would_start": "Vorsorgliche Sperre: {name} läuft an (Spielraum {room:.1f} kW, Anlauf {kw:.1f} kW), eine Sperre hätte diesen Anlauf verschoben",
        "pc_not_followed": "Vorsorgliche Sperre: {name} hat die Sperre nicht übernommen, das Gerät wird {min} min ausgelassen",
        "pc_no_sensor": "Vorsorgliche Sperre: {name} hat keinen Leistungssensor und keine Läuft-Entität, ohne sie wird nie vorsorglich gesperrt",
        "pc_off": "Vorsorgliche Sperre: {name} freigegeben (Anlaufleistung ist 0)",
        "pc_back": "Vorsorgliche Sperre: {name} freigegeben",
        "pc_day": "Vorsorgliche Sperre: {name} freigegeben, Tagesgrenze ({h:g} h) erreicht, heute keine weitere vorsorgliche Sperre",
        "pc_suggest": "Gemessene Anlaufspitze: {kw:.1f} kW (Median aus {n} Läufen)",
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
        "res_freeze": "Akku-Reserve: {name} bleibt beim aktuellen Ladestand (Minimum {value} %) für das Risiko {start}–{end}",
        "step_start": "{name}: Mindest-Ladestand folgt dem Ladestand zurück auf {target} % (jetzt {value} %), damit der Akku nicht auf einmal aus dem Netz lädt",
        "step_done": "{name}: Mindest-Ladestand wieder {target} %",
        "recharge_start": "{name}: Nachladezeit, Mindest-Ladestand wieder {target} %, der Akku wird aus dem Netz nachgeladen",
        "step_end": "{name}: Mindest-Ladestand wieder {target} % ({reason})",
        "step_changed": "{name}: Mindest-Ladestand inzwischen anders eingestellt, schrittweises Zurückstellen beendet",
        "step_fail": "{name}: Mindest-Ladestand nicht nachgezogen ({err})",
        "res_fail": "Akku-Reserve: {name} nicht gesetzt ({err})",
        "res_back_fail": "Akku-Reserve: {name} nicht zurückgestellt ({err})",
        "res_end": "Akku-Reserve beendet ({reason}): {name} wieder wie vorher",
        "res_end_changed": "Akku-Reserve beendet ({reason}): {name} inzwischen anders eingestellt, nichts geändert",
        "plan_pause": "Ladeplan: Laden pausiert (außerhalb der geplanten Zeiten)",
        "plan_go": "Ladeplan: Laden freigegeben",
        "plan_fail": "Ladeplan: Befehl fehlgeschlagen ({err}), neuer Versuch in {min} Min.",
        "err_timeout": "keine Antwort innerhalb von {s} s",
        "err_slow": "keine Antwort innerhalb von {s} s, der Befehl läuft weiter",
        "slow": "{what} (Gerät antwortet langsam, über {s} s; der Befehl läuft weiter)",
        "slow_note": "(Gerät antwortet langsam, der Befehl läuft weiter)",
        "late_fail": "Befehl {what} ist nach langer Wartezeit doch fehlgeschlagen ({err})",
        "error": "Fehler: {what} ({err})",
        "observed": "(beobachtet)",
    },
    "en": {
        "ahead": "Ahead ({why}): {text}",
        "watch": "Observe only: {name} would be lowered by {kw:.1f} kW ({excess:.1f} kW too much), nothing was sent (Observe only is on at the device)",
        "corrected": "Quarter hour {start} corrected: {old:.2f} kW -> {new:.2f} kW (value from the meter)",
        "removed": "Quarter hour {start} taken out of the record: {old:.2f} kW was no measurement",
        "watch_wb": "Observe only: {name} would be limited from {cur} A to {new} A (−{kw:.1f} kW, {excess:.1f} kW too much), nothing was sent (Observe only is on at the device)",
        "watch_wb1": "Observe only: {name} would be switched to 1 phase with {new} A ({excess:.1f} kW too much), nothing was sent (Observe only is on at the device)",
        "wb_twice": "Wallbox {a} and evcc loadpoint {b} charge at the same time with nearly the same power ({kw:.1f} kW). Is it the same wallbox? Please enter it only once.",
        "grid_differ": "Grid import: your sensor shows {a:.1f} kW, evcc shows {b:.1f} kW. The guard works with your sensor.",
        "grid_backup_on": "Grid import: your sensor has no usable value, the guard temporarily uses the value from evcc ({b:.1f} kW).",
        "grid_backup_off": "Grid import: your sensor is delivering again, the guard works with it again.",
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
        "wb2_down": "{name} {cur} A -> {new} A (2-phase, {excess:.1f} kW too much)",
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
        "pc_lock": "Precautionary lock: {name} locked (headroom {room:.1f} kW, start {kw:.1f} kW)",
        "pc_would_lock": "Precautionary lock: {name} would have been locked (headroom {room:.1f} kW, start {kw:.1f} kW), nothing was sent",
        "pc_free": "Precautionary lock: {name} released (headroom {room:.1f} kW)",
        "pc_would_free": "Precautionary lock: {name} would have been released (headroom {room:.1f} kW)",
        "pc_max": "Precautionary lock: {name} released after the maximum time ({min:.0f} min), the next precautionary lock at the earliest in {min:.0f} min",
        "pc_running": "Precautionary lock: {name} runs despite the lock, lock taken back (the normal control takes over)",
        "pc_would_start": "Precautionary lock: {name} starts (headroom {room:.1f} kW, start {kw:.1f} kW), a lock would have put this start off",
        "pc_not_followed": "Precautionary lock: {name} did not take the lock, the device is left alone for {min} min",
        "pc_no_sensor": "Precautionary lock: {name} has no power sensor and no running entity, without one it is never locked in advance",
        "pc_off": "Precautionary lock: {name} released (start power is 0)",
        "pc_back": "Precautionary lock: {name} released",
        "pc_day": "Precautionary lock: {name} released, daily limit ({h:g} h) reached, no further precautionary lock today",
        "pc_suggest": "Measured start peak: {kw:.1f} kW (median of {n} runs)",
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
        "res_freeze": "Battery reserve: {name} stays at its current state of charge (minimum {value} %) for the risk {start}–{end}",
        "step_start": "{name}: the minimum state of charge follows the charge back up to {target} % (now {value} %), so the battery does not charge from the grid all at once",
        "step_done": "{name}: minimum state of charge back at {target} %",
        "recharge_start": "{name}: recharge time, minimum state of charge back at {target} %, the battery is charged from the grid",
        "step_end": "{name}: minimum state of charge back at {target} % ({reason})",
        "step_changed": "{name}: minimum state of charge was changed meanwhile, stepping back ended",
        "step_fail": "{name}: minimum state of charge not raised ({err})",
        "res_fail": "Battery reserve: {name} not set ({err})",
        "res_back_fail": "Battery reserve: {name} not put back ({err})",
        "res_end": "Battery reserve ended ({reason}): {name} back as before",
        "res_end_changed": "Battery reserve ended ({reason}): {name} was changed meanwhile, nothing done",
        "plan_pause": "Charge plan: charging paused (outside the planned times)",
        "plan_go": "Charge plan: charging allowed",
        "plan_fail": "Charge plan: command failed ({err}), next try in {min} min",
        "err_timeout": "no answer within {s} s",
        "err_slow": "no answer within {s} s, the command goes on",
        "slow": "{what} (device answers slowly, over {s} s; the command goes on)",
        "slow_note": "(device answers slowly, the command goes on)",
        "late_fail": "Command {what} failed after all, after a long wait ({err})",
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


def _kw(lang: str, v: float) -> str:
    s = f"{v:.1f}"
    return s.replace(".", ",") if lang == "de" else s


def limit_note(lang: str | None, limit_kw: float, effective_kw: float) -> str | None:
    """One sentence when the effective limit is above the set one (0.16.0, user case: 4 kW set, 9.7 kW month peak); else None."""
    if effective_kw <= limit_kw + 0.005:
        return None
    lg = language(lang)
    if lg == "de":
        return (f"Wirksam {_kw(lg, effective_kw)} kW statt {_kw(lg, limit_kw)} kW, weil die Monatsspitze höher ist: bis dorthin kostet "
                "ein höherer Bezug nichts mehr, deshalb greift der Wächter erst darüber ein.")
    return (f"Effective {_kw(lg, effective_kw)} kW instead of {_kw(lg, limit_kw)} kW, because the month peak is higher: up to it a "
            "higher import costs nothing more, so the guard only steps in above it.")
