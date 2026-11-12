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


def ws_session():
    """Minimal websocket client (package `websockets`): returns send(msg) -> list of messages up to the result."""
    from websockets.sync.client import connect

    ws = connect(BASE.replace("http", "ws") + "/api/websocket", max_size=None)
    ws.recv()
    ws.send(json.dumps({"type": "auth", "access_token": TOKEN}))
    if json.loads(ws.recv()).get("type") != "auth_ok":
        raise RuntimeError("websocket auth failed")
    counter = [0]

    def call(msg, want_event=False):
        counter[0] += 1
        msg = {**msg, "id": counter[0]}
        ws.send(json.dumps(msg))
        out = []
        for _ in range(8):
            m = json.loads(ws.recv())
            if m.get("id") != msg["id"]:
                continue
            out.append(m)
            if m.get("type") == "result" and not (want_event and m.get("success")):
                break
            if m.get("type") == "event":
                break
        return out

    return call, ws


def flow_finish(path, init_body, user_input):
    """Runs a flow to its end: every form gets the values of `user_input` it has fields for (the rest stay at their defaults);
    a menu takes `user_input["_menu"]` or else "finish"."""
    s, d = api("POST", path, init_body)
    if s != 200:
        return None, f"init {s} {d}"
    for _ in range(12):
        if d.get("type") == "create_entry":
            return d, ""
        if d.get("type") == "abort":
            return None, f"abort {d.get('reason')}"
        if d.get("type") == "menu":
            opts = list(d.get("menu_options") or [])
            pick = user_input.get("_menu") if user_input.get("_menu") in opts else ("finish" if "finish" in opts else opts[-1])
            s, d = api("POST", f"{path}/{d['flow_id']}", {"next_step_id": pick})
        elif d.get("type") == "form":
            names = {f.get("name") for f in (d.get("data_schema") or [])}
            s, d = api("POST", f"{path}/{d['flow_id']}", {k: v for k, v in user_input.items() if k in names})
        else:
            return None, f"unexpected {d.get('type')}"
        if s != 200:
            return None, f"step {s} {d}"
        if d.get("errors"):
            return None, f"errors {d['errors']}"
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
    fields = {f.get("name"): f for f in (d.get("data_schema") or [])}
    sel = ((fields.get("grid_power") or {}).get("selector") or {}).get("entity") or {}
    log(bool(sel) and not sel.get("device_class") and "device_class" not in str(sel), "Netzbezug-Feld filtert nicht nach Geraeteklasse (Issue 1)", str(sel))
    s2, d2 = api("POST", f"/api/config/config_entries/flow/{d['flow_id']}", {"name": "Viertelstunden-Wächter", "grid_power": "sensor.netz_ohne_einheit"})
    log(s2 == 200 and d2.get("type") == "form" and (d2.get("errors") or {}).get("grid_power") == "not_power", "Sensor ohne Einheit wird mit klarem Fehler abgelehnt", str(d2.get("errors")))
    api("DELETE", f"/api/config/config_entries/flow/{d['flow_id']}")
    # the assistant: grid import -> sign check -> limit -> devices (menu)
    s, d = api("POST", "/api/config/config_entries/flow", {"handler": "viertelstunden_waechter", "show_advanced_options": False})
    s, d = api("POST", f"/api/config/config_entries/flow/{d['flow_id']}", {"name": "Viertelstunden-Wächter", "grid_power": "sensor.netzbezug"})
    gc_fields = {f.get("name") for f in (d.get("data_schema") or [])}
    log(str(d.get("step_id")).startswith("grid_check") and "grid_invert" in gc_fields,
        "Assistent Schritt 2: Vorzeichen-Pruefung mit Schalter 'Vorzeichen umkehren'", f"{d.get('step_id')} {sorted(gc_fields)} {d.get('description_placeholders')}")
    s, d = api("POST", f"/api/config/config_entries/flow/{d['flow_id']}", {})
    lim_fields = {f.get("name") for f in (d.get("data_schema") or [])}
    log(str(d.get("step_id")).startswith("limit") and {"limit_kw", "margin_kw"} <= lim_fields,
        "Assistent Schritt 3: Grenze mit Hinweis auf die hoechste Viertelstunde", f"{d.get('step_id')} {d.get('description_placeholders')}")
    s, d = api("POST", f"/api/config/config_entries/flow/{d['flow_id']}", {"limit_kw": 10.0, "margin_kw": 0.5})
    opts = list(d.get("menu_options") or [])
    log(d.get("type") == "menu" and "add_wallbox" in opts and "finish" in opts, "Assistent Schritt 4: Geraete-Menue (Wallbox, Abschliessen)", f"{d.get('type')} {opts}")
    s, d = api("POST", f"/api/config/config_entries/flow/{d['flow_id']}", {"next_step_id": "add_wallbox"})
    wb_fields = {f.get("name") for f in (d.get("data_schema") or [])}
    log(d.get("step_id") == "add_wallbox" and "power_invert" in wb_fields, "Wallbox im Assistenten, mit 'Vorzeichen umkehren' beim Leistungssensor", str(sorted(wb_fields)))
    api("DELETE", f"/api/config/config_entries/flow/{d['flow_id']}")
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
    share = [e for e in ents if e["entity_id"].startswith("switch.") and ("anonyme_daten_teilen" in e["entity_id"] or "share_anonymous_data" in e["entity_id"])]
    for l in ('de', 'en'):
        pv = urllib.request.urlopen(f"{BASE}/viertelstunden_waechter/vorschau/geraete-check-{l}.webp", timeout=20)
        log(pv.status == 200 and pv.headers.get_content_type() == 'image/webp', f'Vorschau {l} wird lokal ausgeliefert', str(pv.status))
    log(len(share) == 1 and share[0]["state"] == "off", "Anonyme Daten teilen: ein Schalter, aus (nur mit Zustimmung)", str([(e["entity_id"], e["state"]) for e in share]))
    fb = [e["entity_id"] for e in ents if e["entity_id"].startswith(("text.", "button.")) and "ruckmeldung" in e["entity_id"]]
    log(len(fb) == 2, "Rueckmeldung: Textfeld und Knopf da", str(fb))
    need = ["select.viertelstunden_wachter_betriebsart", "sensor.viertelstunden_wachter_status", "number.viertelstunden_wachter_grenze",
            "switch.viertelstunden_wachter_vorausschauend_drosseln_nach_prognose", "switch.viertelstunden_wachter_vorwarnung_vor_einem_eingriff",
            "switch.viertelstunden_wachter_wochenbericht", "sensor.viertelstunden_wachter_wochenbericht", "sensor.viertelstunden_wachter_ladeplan",
            "switch.viertelstunden_wachter_akku_reserve_vor_einer_spitze", "switch.viertelstunden_wachter_ki_erklarer",
            "sensor.viertelstunden_wachter_erklarung_des_tages", "sensor.viertelstunden_wachter_gerate_check"]
    missing = [n for n in need if n not in names]
    log(not missing, "Wichtige Entitaeten vorhanden", f"fehlen: {missing}" if missing else "")
    if missing:
        print("vorhandene:", "\n".join(names))

    # ---------- Geraete-Check (0.15): nur mit "Anonyme Daten teilen"; in der Testinstanz bleibt der Schalter aus ----------
    gc_st = state("sensor.viertelstunden_wachter_gerate_check") or {}
    gc_dev = (gc_st.get("attributes") or {}).get("devices") or []
    log(gc_st.get("state") == "sharing_off" and (gc_st.get("attributes") or {}).get("checked_at") is None,
        "Geraete-Check: ohne Datenfreigabe kein Check und keine Anfrage", f"{gc_st.get('state')} {(gc_st.get('attributes') or {}).get('checked_at')}")
    log(sorted(d.get("name") for d in gc_dev) == ["Akku", "Poolpumpe", "Wallbox"] and all(d.get("status") == "none" and not d.get("found") for d in gc_dev),
        "Geraete-Check: alle Geraete ausser dem Auto gelistet, ohne Befund", str([(d.get("name"), d.get("status")) for d in gc_dev]))
    for kind, field in (("battery", "battery_power_entity"), ("switch", "device_type")):
        s, d = api("POST", "/api/config/config_entries/subentries/flow", {"handler": [entry_id, kind]})
        names_f = {f.get("name") for f in (d.get("data_schema") or [])}
        log(field in names_f, f"Geraete-Check: Feld '{field}' beim Geraet '{kind}'", str(sorted(names_f)))
        if d.get("flow_id"):
            api("DELETE", f"/api/config/config_entries/subentries/flow/{d['flow_id']}")

    def val(eid):
        st = state(eid)
        return st["state"] if st else None

    # ---------- Ladeplan eines Auto-Planers (optional) ----------
    fc = "sensor.viertelstunden_wachter_typischer_bezug_jetzt_prognose"
    cp0 = wait_for(lambda: ((state(fc) or {}).get("attributes", {}).get("car_plan") or None), 180) or {}  # the first forecast takes a moment
    log(cp0.get("used") is False and cp0.get("configured") == 0, "Ohne Ladeplan-Verbindung aendert sich nichts (car_plan used = false)", str(cp0))
    pk = (state("sensor.viertelstunden_wachter_erwartete_spitze_in_24_h_prognose") or {}).get("attributes", {})
    hh, hs = pk.get("hours_house") or [], pk.get("hours") or []
    log(len(hh) == len(hs) and len(hh) > 0 and all(a["t"] == b["t"] for a, b in zip(hh, hs))
        and all((a["high"] or 0) <= (b["high"] or 0) + 1e-6 for a, b in zip(hh, hs)),
        "Hausprognose ohne Wallbox fuer Lade-Planer (hours_house, nie hoeher als hours)", f"{len(hh)}/{len(hs)}")
    s_o, d_o = api("POST", "/api/config/config_entries/options/flow", {"handler": entry_id})
    s_o2, d_o2 = api("POST", f"/api/config/config_entries/options/flow/{d_o['flow_id']}",
                     {"grid_power": "sensor.netzbezug", "mains_voltage": 230, "startup_mode": "restore", "charge_plan_entities": ["sensor.test_ladeplan"]})
    log(s_o == 200 and d_o2.get("type") == "create_entry", "Ladeplan-Sensor kann in den Einstellungen gewaehlt werden", f"{d_o.get('type')} / {d_o2.get('type')}")

    def car_plan_used():
        a = (state(fc) or {}).get("attributes", {}).get("car_plan", {})
        return a if a.get("used") is True else None

    cp1 = wait_for(car_plan_used, 120)
    log(bool(cp1) and cp1.get("windows") == 1 and cp1.get("configured") == 1, "Mit Ladeplan-Verbindung wird der Plan gelesen (1 Fenster)", str(cp1))

    # ---------- Alterskontrolle des Messwerts ----------
    st_id = "sensor.viertelstunden_wachter_status"

    def set_grid(sensor, max_age):
        s1, d1 = api("POST", "/api/config/config_entries/options/flow", {"handler": entry_id})
        s2, d2 = api("POST", f"/api/config/config_entries/options/flow/{d1['flow_id']}",
                     {"grid_power": sensor, "mains_voltage": 230, "startup_mode": "restore", "max_reading_age_s": max_age})
        return d2.get("type") == "create_entry"

    a0 = (state(st_id) or {}).get("attributes", {})
    log(a0.get("grid_stale") is False and isinstance(a0.get("grid_age_s"), (int, float)), "Messwert frisch: grid_stale false und Alter wird gemeldet", f"{a0.get('grid_stale')} / {a0.get('grid_age_s')}")
    log(set_grid("sensor.netzbezug_still", 30), "Alterskontrolle: Sensor, der nie neu schreibt, und Höchstalter 30 s eingestellt")
    ok = wait_for(lambda: (state(st_id) or {}).get("attributes", {}).get("grid_stale") is True, 120)
    log(bool(ok), "Messwert aelter als 30 s: gilt als fehlend (grid_stale)", str((state(st_id) or {}).get("attributes", {}).get("grid_age_s")))
    ok = wait_for(lambda: (state(st_id) or {}).get("state") == "no_data", 240)
    log(bool(ok), "nach 90 s ohne frischen Messwert: Status keine Daten, es wird nichts geschaltet", str((state(st_id) or {}).get("state")))
    log(set_grid("sensor.netzbezug", 120), "wieder der Sensor, der jede Minute schreibt, Höchstalter 120 s")
    ok = wait_for(lambda: (state(st_id) or {}).get("attributes", {}).get("grid_stale") is False and (state(st_id) or {}).get("state") != "no_data", 240)
    log(bool(ok), "frischer Messwert: normal weiter", str((state(st_id) or {}).get("state")))

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
    # late in a quarter hour with little energy so far the budget is large: the guard acts when the next one begins
    st = wait_for(lambda: val("sensor.viertelstunden_wachter_status") in ("would_intervene",), 960, 10)
    log(bool(st), "Beobachtungsmodus erkennt die Ueberschreitung (13,8 kW, spaetestens ab der naechsten Viertelstunde)", str(val("sensor.viertelstunden_wachter_status")))
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
    back = wait_for(lambda: float(val("input_number.wb_strom")) == 16.0 and val("input_boolean.pool_pumpe") == "on", 900, 10)  # several levers are given back one after another
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
    # the export and the learning need one finished quarter hour; since 0.14.0 the quarter hour the guard started in is not recorded,
    # so the first one ends up to 30 minutes after the start
    lq = wait_for(lambda: val("sensor.viertelstunden_wachter_letzte_viertelstunde") not in (None, "unknown", "unavailable"), 1900, 15)
    log(bool(lq), "Erste Viertelstunde abgeschlossen und gelernt", f"{val('sensor.viertelstunden_wachter_letzte_viertelstunde')} kW")
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
    # the generated dashboard: save it into a dashboard and render EVERY markdown card with the strict template engine
    try:
        call, ws = ws_session()
        r = call({"type": "lovelace/dashboards/create", "url_path": "waechter-test", "title": "Test", "icon": "mdi:shield", "show_in_sidebar": False, "require_admin": False, "mode": "storage"})
        log(bool(r) and r[0].get("success"), "Dashboard-Seite fuer den Test angelegt", str(r[0].get("error")) if r else "")
        s, d = svc("viertelstunden_waechter", "create_dashboard", {"dashboard": "waechter-test"}, resp=True)
        log(s == 400 or s == 422, "Dienst 'Dashboard erstellen' nimmt kein Dashboard als Ziel mehr an (kein Schreibweg)", f"HTTP {s}")
        s, d = svc("viertelstunden_waechter", "create_dashboard", {}, resp=True)
        gen = (d.get("service_response") or {}).get("config") if isinstance(d, dict) else None
        log(s == 200 and bool(gen) and gen.get("views"), "Dienst 'Dashboard erstellen' liefert die Konfiguration", f"{len((gen or {}).get('views', []))} Ansichten")
        sv = call({"type": "lovelace/config/save", "url_path": "waechter-test", "config": gen})
        log(bool(sv) and sv[0].get("success"), "Konfiguration als Administrator in das Test-Dashboard gespeichert", str(sv[0].get("error")) if sv else "")
        cfg = call({"type": "lovelace/config", "url_path": "waechter-test"})[0].get("result") or {}
        views = cfg.get("views", [])
        log([v.get("path") for v in views] == ["waechter", "heute", "statistik"], "Dashboard hat die Ansichten Waechter, Heute (Handy), Statistik", str([v.get("path") for v in views]))
        cards = [c for v in views for sec in v.get("sections", []) for c in sec.get("cards", []) if c.get("type") == "markdown"]
        cards += [c["card"] for v in views for sec in v.get("sections", []) for c in sec.get("cards", [])
                  if c.get("type") == "conditional" and (c.get("card") or {}).get("type") == "markdown"]   # the explanation of the day
        bad = []
        for c in cards:
            m = call({"type": "render_template", "template": c["content"], "timeout": 20, "strict": True}, want_event=True)
            res = m[-1]
            if res.get("type") == "result" and not res.get("success"):
                bad.append(f"{c['content'][:60]!r}: {res.get('error')}")
            elif res.get("type") == "event" and not str(res["event"].get("result", "x")).strip():
                bad.append(f"{c['content'][:60]!r}: leer")
        log(len(cards) >= 8 and not bad, f"Alle {len(cards)} Markdown-Karten des Dashboards rendern ohne Fehler (strenger Modus)", "; ".join(bad)[:300])
        ws.close()
    except Exception as err:  # noqa: BLE001
        log(False, "Dashboard-Pruefung", f"{type(err).__name__}: {err}")
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


if __name__ == "__main__":  # importing this file (itest_evcc.py uses its helpers) must not run the whole test
    main()
    fails = [l for ok, l in REPORT if not ok]
    print("\n===== ERGEBNIS: %d von %d Pruefungen bestanden =====" % (len(REPORT) - len(fails), len(REPORT)))
    for l in fails:
        print(l)
    open(__file__.replace("itest.py", "report.txt"), "w", encoding="utf-8").write("\n".join(l for _, l in REPORT))
