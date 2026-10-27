"""Installationstest des Viertelstunden-Waechters gegen eine frische Home-Assistant-Instanz (Docker, localhost)."""
import json
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://localhost:18123"
CONTAINER = "vw-test"
REPORT = []
TOKEN = None


def log(ok, name, detail=""):
    line = f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else "")
    REPORT.append((ok, line))
    print(line, flush=True)


def api(method, path, body=None, form=None, token=True, ok_codes=(200, 201)):
    url = BASE + path
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if token and TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            txt = r.read().decode()
            return r.status, (json.loads(txt) if txt.strip().startswith(("{", "[")) else txt)
    except urllib.error.HTTPError as e:
        txt = e.read().decode()
        try:
            return e.code, json.loads(txt)
        except ValueError:
            return e.code, txt


def wait_ready(timeout=420):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            s, _ = api("GET", "/api/onboarding", token=False)
            if s == 200:
                return True
        except Exception:
            pass
        time.sleep(5)
    return False


def onboard():
    global TOKEN
    pw = secrets.token_urlsafe(16)
    cid = BASE + "/"
    s, d = api("POST", "/api/onboarding/users", {"client_id": cid, "name": "Test", "username": "testuser", "password": pw, "language": "de"}, token=False)
    if s != 200:
        return False, f"onboarding users {s} {d}"
    s, d = api("POST", "/auth/token", form={"grant_type": "authorization_code", "code": d["auth_code"], "client_id": cid}, token=False)
    if s != 200:
        return False, f"token {s} {d}"
    TOKEN = d["access_token"]
    return True, ""


def state(eid):
    s, d = api("GET", f"/api/states/{eid}")
    return d if s == 200 else None


def states_like(sub):
    s, d = api("GET", "/api/states")
    return [x for x in d if sub in x["entity_id"]]


def svc(domain, service, data=None, resp=False):
    return api("POST", f"/api/services/{domain}/{service}" + ("?return_response" if resp else ""), data or {})


def wait_for(pred, timeout, step=5):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = pred()
        if v:
            return v
        time.sleep(step)
    return None


def flow_finish(path, init_body, user_input):
    s, d = api("POST", path, init_body)
    if s != 200:
        return None, f"init {s} {d}"
    for _ in range(4):
        if d.get("type") == "create_entry":
            return d, ""
        if d.get("type") == "abort":
            return None, f"abort {d.get('reason')}"
        if d.get("type") == "form":
            s, d = api("POST", f"{path}/{d['flow_id']}", user_input)
            if s != 200:
                return None, f"step {s} {d}"
            if d.get("errors"):
                return None, f"errors {d['errors']}"
        else:
            return None, f"unexpected {d.get('type')}"
    return (d if d.get("type") == "create_entry" else None), "no create_entry"


def main():
    if not wait_ready():
        log(False, "Home Assistant startet")
        return
    log(True, "Home Assistant startet (frische Instanz, onboarding offen)")
    ok, msg = onboard()
    log(ok, "Benutzer und Token fuer den Test angelegt", msg)
    if not ok:
        return
    # warten bis die simulierten Entitaeten da sind
    ok = wait_for(lambda: state("sensor.netzbezug") and state("sensor.netzbezug")["state"] not in ("unknown", "unavailable"), 120)
    log(bool(ok), "Simuliertes Haus (Netzbezug, Wallbox, Pool) laeuft")

    # ---------- Einrichtung ----------
    s, d = api("GET", "/api/config")
    log(s == 200, "Version der Testinstanz", d.get("version") if isinstance(d, dict) else str(d))
    s, d = api("POST", "/api/config/config_entries/flow", {"handler": "viertelstunden_waechter", "show_advanced_options": False})
    log(s == 200 and d.get("type") == "form" and d.get("step_id") == "user", "Integration wird im Dialog angeboten (Config Flow)", f"{s} {d.get('type')} {d.get('step_id')}")
    entry, err = flow_finish("/api/config/config_entries/flow", {"handler": "viertelstunden_waechter", "show_advanced_options": False},
                             {"name": "Viertelstunden-Wächter", "grid_power": "sensor.netzbezug", "limit_kw": 10.0, "margin_kw": 0.5})
    log(entry is not None, "Integration von Grund auf eingerichtet", err)
    if not entry:
        return
    entry_id = (entry.get("result") or {}).get("entry_id") if isinstance(entry.get("result"), dict) else entry.get("entry_id")
    if not entry_id:
        s, lst = api("GET", "/api/config/config_entries/entry?domain=viertelstunden_waechter")
        entry_id = lst[0]["entry_id"]
    log(bool(entry_id), "Eintrag angelegt", str(entry_id))

    # zweite Instanz darf nicht moeglich sein (single_config_entry)
    s, d = api("POST", "/api/config/config_entries/flow", {"handler": "viertelstunden_waechter"})
    log(s == 200 and d.get("type") == "abort", "Zweiter Eintrag wird abgelehnt (nur ein Waechter)", f"{d.get('type')} {d.get('reason')}")

    subs = [
        ("wallbox", {"name": "Wallbox", "priority": 1, "power_entity": "sensor.wallbox_leistung", "current_entity": "input_number.wb_strom", "min_current": 6, "max_current": 16}),
        ("switch", {"name": "Poolpumpe", "priority": 2, "switch_entity": "input_boolean.pool_pumpe", "power_entity": "sensor.pool_leistung", "min_power_w": 150, "power_w": 750, "max_off_min": 0, "pause_min": 0}),
        ("battery", {"name": "Akku", "priority": 10, "soc_entity": "sensor.akku_ladestand", "min_soc": 30, "release_entity_1": "input_number.akku_ausgang_w", "release_value_1": "2000", "power_w": 800, "max_off_min": 0, "restore_original": True, "reserve_entity": "input_number.akku_ausgang_w", "reserve_value": "50", "reserve_lead_min": 60}),
        ("vehicle", {"name": "Auto", "soc_entity": "sensor.auto_ladestand", "target_soc": 80, "capacity_kwh": 60, "departure_entity": "input_datetime.abfahrt", "charge_kw_max": 11, "charge_kw_min": 1.4, "house_base_kw": 0.5, "charge_efficiency": 90}),
    ]
    for kind, data in subs:
        res, err = flow_finish("/api/config/config_entries/subentries/flow", {"handler": [entry_id, kind]}, data)
        log(res is not None, f"Geraet hinzugefuegt: {kind}", err)

    time.sleep(20)
    ents = states_like("viertelstunden_wachter")
    names = sorted(e["entity_id"] for e in ents)
    log(len(ents) >= 37, "Entitaeten der Integration angelegt", f"{len(ents)} Stueck")
    need = ["select.viertelstunden_wachter_betriebsart", "sensor.viertelstunden_wachter_status", "number.viertelstunden_wachter_grenze",
            "switch.viertelstunden_wachter_vorausschauend_drosseln_nach_prognose", "switch.viertelstunden_wachter_vorwarnung_vor_einem_eingriff",
            "switch.viertelstunden_wachter_wochenbericht", "sensor.viertelstunden_wachter_wochenbericht", "sensor.viertelstunden_wachter_ladeplan",
            "switch.viertelstunden_wachter_akku_reserve_vor_einer_spitze", "switch.viertelstunden_wachter_ki_erklarer",
            "sensor.viertelstunden_wachter_erklarung_des_tages"]
    missing = [n for n in need if n not in names]
    log(not missing, "Wichtige Entitaeten vorhanden", f"fehlen: {missing}" if missing else "")
    if missing:
        print("vorhandene:", "\n".join(names))

    def val(eid):
        st = state(eid)
        return st["state"] if st else None

    log(val("select.viertelstunden_wachter_betriebsart") == "observe", "Neue Installation startet im Beobachtungsmodus", str(val("select.viertelstunden_wachter_betriebsart")))
    defaults = {
        "switch.viertelstunden_wachter_vorausschauend_drosseln_nach_prognose": "off",
        "switch.viertelstunden_wachter_vorwarnung_vor_einem_eingriff": "off",
        "switch.viertelstunden_wachter_wochenbericht": "on",
        "switch.viertelstunden_wachter_meldung_bei_eingriff": "on",
        "switch.viertelstunden_wachter_bereits_erreichte_spitze_nutzen": "on",
        "switch.viertelstunden_wachter_lastprognose_lernen_und_anzeigen": "on",
        "switch.viertelstunden_wachter_ladeplan_auch_ausfuhren": "off",
        "switch.viertelstunden_wachter_akku_reserve_vor_einer_spitze": "off",
        "switch.viertelstunden_wachter_ki_erklarer": "off",
    }
    bad = {k: val(k) for k, v in defaults.items() if val(k) != v}
    log(not bad, "Standardwerte der Schalter wie dokumentiert", str(bad) if bad else "")

    # ---------- Beobachtungsmodus ----------
    svc("input_boolean", "turn_on", {"entity_id": "input_boolean.auto_laedt"})
    svc("input_number", "set_value", {"entity_id": "input_number.hauslast_w", "value": 2000})
    st = wait_for(lambda: val("sensor.viertelstunden_wachter_status") in ("would_intervene",), 120)
    log(bool(st), "Beobachtungsmodus erkennt die Ueberschreitung (13,8 kW)", str(val("sensor.viertelstunden_wachter_status")))
    log(float(val("input_number.wb_strom")) == 16.0, "Beobachtungsmodus schaltet nichts (Wallbox bleibt 16 A)", str(val("input_number.wb_strom")))

    # ---------- Aktiv ----------
    svc("select", "select_option", {"entity_id": "select.viertelstunden_wachter_betriebsart", "option": "active"})
    low = wait_for(lambda: float(val("input_number.wb_strom")) < 16.0, 150)
    log(bool(low), "Aktiv: Wallbox wird gesenkt (echter Eingriff)", f"{val('input_number.wb_strom')} A")
    wait_for(lambda: float(val("input_number.wb_strom")) <= 6.0, 240)
    log(float(val("input_number.wb_strom")) >= 6.0, "Wallbox wird nie unter das Minimum gesenkt und nie gestoppt", f"{val('input_number.wb_strom')} A")
    for _ in range(12):
        if val("input_boolean.pool_pumpe") == "off":
            break
        time.sleep(10)
    st = state("sensor.viertelstunden_wachter_status")
    today = (st or {}).get("attributes", {}).get("today", [])
    log(bool(today), "Protokoll mit Gruenden vorhanden", (today[-1] if today else "")[:100])
    txt = "\n".join(today)
    log("nicht umgesetzt" not in txt, "Rueckmeldung: kein Geraet meldet 'nicht umgesetzt' (simuliertes Haus folgt sofort)")
    # Eingriffe protokolliert
    cnt = state("sensor.viertelstunden_wachter_eingriffe_heute")
    log(cnt is not None and cnt["state"] not in ("unknown", "unavailable") and float(cnt["state"]) >= 1, "Eingriffe heute gezaehlt", str(cnt["state"]) if cnt else "")

    # ---------- Rueckgabe ----------
    svc("input_boolean", "turn_off", {"entity_id": "input_boolean.auto_laedt"})
    svc("input_number", "set_value", {"entity_id": "input_number.hauslast_w", "value": 300})
    back = wait_for(lambda: float(val("input_number.wb_strom")) == 16.0 and val("input_boolean.pool_pumpe") == "on", 420, 10)
    log(bool(back), "Rueckgabe: Wallbox wieder 16 A und Pool wieder an nach Ende der Last",
        f"{val('input_number.wb_strom')} A, Pool {val('input_boolean.pool_pumpe')}")
    st = wait_for(lambda: val("sensor.viertelstunden_wachter_status") == "ready", 120)
    log(bool(st), "Status wieder 'bereit'", str(val("sensor.viertelstunden_wachter_status")))

    # ---------- Dienste ----------
    s, d = svc("viertelstunden_waechter", "create_dashboard", {}, resp=True)
    yaml_text = (d.get("service_response") or {}).get("yaml", "") if isinstance(d, dict) else ""
    log(s == 200 and "views:" in yaml_text and "viertelstunden_wachter_status" in yaml_text, "Dienst 'Dashboard erstellen' liefert YAML mit den eigenen Entitaeten", f"{len(yaml_text)} Zeichen")
    s, d = svc("viertelstunden_waechter", "send_week_report", {"current_week": True, "push": False}, resp=True)
    txt = (d.get("service_response") or {}).get("text", "") if isinstance(d, dict) else ""
    log(s == 200 and "Wochenbericht" in txt, "Dienst 'Wochenbericht senden' erzeugt den Bericht", txt.replace("\n", " | ")[:140])
    s, d = svc("viertelstunden_waechter", "import_history", {"days": [{"date": "2026-10-01", "kw": 7.8, "at": "18:15"}], "months": [{"month": "2026-10", "peak_kw": 9.1}]}, resp=True)
    log(s == 200 and (d.get("service_response") or {}).get("days") == 1, "Dienst 'Verlauf importieren'", str(d.get("service_response") if isinstance(d, dict) else d))
    # the export and the learning need at least one finished quarter hour (the test may start in the middle of one)
    lq = wait_for(lambda: state("sensor.viertelstunden_wachter_letzte_viertelstunde") and
                  state("sensor.viertelstunden_wachter_letzte_viertelstunde")["state"] not in ("unknown", "unavailable"), 960, 15)
    log(bool(lq), "Erste Viertelstunde abgeschlossen und gelernt", (lq or {}).get("state", "") + " kW" if lq else "")
    s, d = svc("viertelstunden_waechter", "export_csv", {"kind": "days", "days": 400, "format": "excel_de"}, resp=True)
    r = (d.get("service_response") or {}) if isinstance(d, dict) else {}
    log(s == 200 and r.get("rows", 0) >= 1 and "date;peak_kw;at" in (r.get("csv") or ""), "Dienst 'Als CSV exportieren' (Tagesspitzen)", f"{r.get('rows')} Zeilen, {r.get('path')}")
    s, d = svc("viertelstunden_waechter", "export_csv", {"kind": "quarters", "days": 2}, resp=True)
    r = (d.get("service_response") or {}) if isinstance(d, dict) else {}
    log(s == 200 and r.get("rows", 0) >= 1 and (r.get("csv") or "").startswith("start,end,import_kw"), "Dienst 'Als CSV exportieren' (Viertelstunden)", f"{r.get('rows')} Zeilen")
    s, d = svc("viertelstunden_waechter", "explain_today", {"push": False}, resp=True)
    r = (d.get("service_response") or {}) if isinstance(d, dict) else {}
    log(s == 200 and r.get("source") == "none" and "AI task" in str(r.get("error")), "Dienst 'Heute erklaeren' ohne KI-Aufgabe: sauberer Hinweis, kein Absturz", str(r.get("error")))
    ex = state("sensor.viertelstunden_wachter_erklarung_des_tages")
    log(ex is not None and ex["state"] not in ("unavailable",), "Sensor 'Erklaerung des Tages'", ex["state"] if ex else "")
    log(float(val("input_number.akku_ausgang_w")) == 800.0, "Akku-Reserve aus: Akku unveraendert", f"{val('input_number.akku_ausgang_w')} W")
    cp = state("sensor.viertelstunden_wachter_ladeplan")
    log(cp is not None, "Ladeplan-Sensor vorhanden", str(cp["state"]) if cp else "")

    # ---------- Neustart: Zustand bleibt, Eingriffe werden freigegeben ----------
    svc("input_boolean", "turn_on", {"entity_id": "input_boolean.auto_laedt"})
    svc("input_number", "set_value", {"entity_id": "input_number.hauslast_w", "value": 2000})
    wait_for(lambda: float(val("input_number.wb_strom")) < 16.0, 150)
    before = val("input_number.wb_strom")
    subprocess.run(["docker", "restart", CONTAINER], check=False, capture_output=True)
    time.sleep(10)
    ok = wait_ready(300)
    log(ok, "Neustart der Instanz mit laufendem Eingriff", f"vorher {before} A")
    # Token bleibt gueltig
    wait_for(lambda: state("select.viertelstunden_wachter_betriebsart") is not None and val("select.viertelstunden_wachter_betriebsart") not in ("unavailable", "unknown"), 200)
    log(val("select.viertelstunden_wachter_betriebsart") == "active", "Betriebsart bleibt nach Neustart erhalten", str(val("select.viertelstunden_wachter_betriebsart")))
    log(val("switch.viertelstunden_wachter_wochenbericht") == "on" and val("switch.viertelstunden_wachter_vorwarnung_vor_einem_eingriff") == "off", "Schalter bleiben nach Neustart erhalten")
    log(val("switch.viertelstunden_wachter_ladeplan_auch_ausfuhren") == "off", "'Ladeplan auch ausfuehren' ist nach Neustart aus")
    log(val("switch.viertelstunden_wachter_ki_erklarer") == "off", "'KI-Erklaerer' ist nach Neustart aus")

    # ---------- Log ----------
    logs = subprocess.run(["docker", "logs", CONTAINER], capture_output=True, text=True).stdout
    errs = [l for l in logs.splitlines() if ("viertelstunden" in l.lower() and ("ERROR" in l or "Traceback" in l or "Exception" in l))]
    log(not errs, "Keine Fehler der Integration im Protokoll", f"{len(errs)} Zeilen" if errs else "")
    for e in errs[:8]:
        print("   ", e[:240])


main()
fails = [l for ok, l in REPORT if not ok]
print("\n===== ERGEBNIS: %d von %d Pruefungen bestanden =====" % (len(REPORT) - len(fails), len(REPORT)))
for l in fails:
    print(l)
open(__file__.replace("itest.py", "report.txt"), "w", encoding="utf-8").write("\n".join(l for _, l in REPORT))
