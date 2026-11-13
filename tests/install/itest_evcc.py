"""The guard with an evcc loadpoint, in ONE fresh Home Assistant, against a real (demo) evcc.

Needs: the Home Assistant test container with tests/install/config_evcc (port 18126, name evcc-ha-test) and a demo evcc:
  docker run -d --name evcc-test -p 17070:7070 evcc/evcc:latest evcc --demo
Home Assistant reaches evcc as http://host.docker.internal:17070. Takes about ten to twenty minutes (real quarter hours).
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import itest as it  # noqa: E402  (the helpers of the single test)

it.BASE = "http://localhost:18126"
it.CONTAINER = "evcc-ha-test"
EVCC_LOCAL = "http://localhost:17070"
EVCC_FROM_HA = "http://host.docker.internal:17070"


def log(ok, name, detail=""):
    it.log(ok, name, detail)


def evcc_lp(n=1):
    with urllib.request.urlopen(EVCC_LOCAL + "/api/state", timeout=15) as r:
        return json.load(r)["loadpoints"][n - 1]


def evcc_post(path):
    req = urllib.request.Request(EVCC_LOCAL + path, method="POST", data=b"")
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode()


def val(eid):
    s = it.state(eid)
    return s["state"] if s else None


def main():
    try:
        lp0 = evcc_lp(1)
    except Exception as err:  # noqa: BLE001
        log(False, "demo evcc is running (port 17070)", str(err))
        return
    evcc_post("/api/loadpoints/1/maxcurrent/16")
    evcc_post("/api/loadpoints/1/mode/now")  # the demo car must charge, otherwise there is nothing to throttle
    charging = it.wait_for(lambda: evcc_lp(1).get("charging") and (evcc_lp(1).get("offeredCurrent") or 0) > 6, 90, 5)
    log(bool(charging), "demo evcc is running and loadpoint 1 charges", f"'{lp0.get('title')}', offered {evcc_lp(1).get('offeredCurrent')} A, ceiling 16 A")
    lp0 = evcc_lp(1)

    if not it.wait_ready():
        log(False, "Home Assistant starts")
        return
    ok, msg = it.onboard()
    log(ok, "test user and token created", msg)
    if not ok:
        return
    ok = it.wait_for(lambda: it.state("sensor.netzbezug") and it.state("sensor.netzbezug")["state"] not in ("unknown", "unavailable"), 120)
    log(bool(ok), "simulated house runs")

    entry, err = it.flow_finish("/api/config/config_entries/flow", {"handler": "viertelstunden_waechter", "show_advanced_options": False},
                                {"name": "Viertelstunden-Wächter", "grid_power": "sensor.netzbezug", "limit_kw": 10.0, "margin_kw": 0.5})
    log(entry is not None, "guard set up", err)
    if not entry:
        return
    s, lst = it.api("GET", "/api/config/config_entries/entry?domain=viertelstunden_waechter")
    entry_id = lst[0]["entry_id"]

    # ---- the dialog: connection is checked when saving ----
    base = {"name": "Carport", "priority": 1, "evcc_url": EVCC_FROM_HA, "evcc_loadpoint": 1, "min_current": 6, "max_current": 16, "evcc_one_phase": False}
    # the demo evcc reports a charging power that does not fit current and phases; the test house derives it from the offered current
    ok = it.wait_for(lambda: float((it.state("sensor.evcc_demo_leistung") or {}).get("state") or 0) > 5000, 120, 5)
    log(bool(ok), "the test house sees the demo car charging (closed loop: power = offered current x 690 W)", str((it.state("sensor.evcc_demo_leistung") or {}).get("state")))
    s, d = it.api("POST", "/api/config/config_entries/subentries/flow", {"handler": [entry_id, "evcc"]})
    log(s == 200 and d.get("type") == "form", "the dialog 'evcc loadpoint' is offered", f"{s} {d.get('type')} {d.get('step_id')}")
    fid = d.get("flow_id")
    fields = {f.get("name") for f in (d.get("data_schema") or [])}
    log({"evcc_url", "evcc_loadpoint", "evcc_password", "min_current", "max_current", "evcc_one_phase"} <= fields, "the dialog has the fields", str(sorted(fields)))
    s, d2 = it.api("POST", f"/api/config/config_entries/subentries/flow/{fid}", {**base, "evcc_url": "http://host.docker.internal:1"})
    log(s == 200 and (d2.get("errors") or {}).get("evcc_url") == "evcc_unreachable", "an address without evcc is refused", str(d2.get("errors")))
    s, d3 = it.api("POST", f"/api/config/config_entries/subentries/flow/{fid}", {**base, "evcc_loadpoint": 9})
    log(s == 200 and (d3.get("errors") or {}).get("evcc_loadpoint") == "evcc_loadpoint", "a loadpoint number that does not exist is refused", str(d3.get("errors")))
    s, d4 = it.api("POST", f"/api/config/config_entries/subentries/flow/{fid}", {**base, "min_current": 20, "max_current": 10})
    log(s == 200 and (d4.get("errors") or {}).get("min_current") == "min_above_max", "minimum above maximum is refused", str(d4.get("errors")))
    it.api("DELETE", f"/api/config/config_entries/subentries/flow/{fid}")
    res, err = it.flow_finish("/api/config/config_entries/subentries/flow", {"handler": [entry_id, "evcc"]}, {**base, "power_entity": "sensor.evcc_demo_leistung"})
    log(res is not None, "evcc loadpoint added as device", err)
    if res is None:
        return
    time.sleep(15)

    # the limit must stay at 10 kW: with "use the peak already reached" a first quarter of 13.8 kW in observe mode lifts it (correctly)
    it.svc("switch", "turn_off", {"entity_id": "switch.viertelstunden_wachter_bereits_erreichte_spitze_nutzen"})
    # ---- observe: nothing is switched ----
    it.svc("input_boolean", "turn_on", {"entity_id": "input_boolean.auto_laedt"})
    it.svc("input_number", "set_value", {"entity_id": "input_number.hauslast_w", "value": 2000})
    st = it.wait_for(lambda: val("sensor.viertelstunden_wachter_status") in ("would_intervene",), 960, 10)
    log(bool(st), "observe mode sees the excess", str(val("sensor.viertelstunden_wachter_status")))
    log(evcc_lp(1)["maxCurrent"] == 16, "observe mode changes nothing in evcc (ceiling stays 16 A)", f"{evcc_lp(1)['maxCurrent']} A")

    # ---- active: the ceiling of evcc is lowered, evcc follows, nothing is stopped ----
    it.svc("select", "select_option", {"entity_id": "select.viertelstunden_wachter_betriebsart", "option": "active"})
    low = it.wait_for(lambda: evcc_lp(1)["maxCurrent"] < 16, 180, 5)
    log(bool(low), "active: the guard lowers evcc's ceiling (real intervention)", f"{evcc_lp(1)['maxCurrent']} A")
    it.wait_for(lambda: evcc_lp(1)["maxCurrent"] <= 6, 300, 5)
    lp = evcc_lp(1)
    log(6 <= lp["maxCurrent"] < 16, "the ceiling never goes below the minimum", f"{lp['maxCurrent']} A")
    log(lp.get("mode") == lp0.get("mode"), "the mode of evcc is untouched (charging is never stopped)", f"{lp.get('mode')}")
    follow = it.wait_for(lambda: (evcc_lp(1).get("effectiveMaxCurrent") or 99) <= lp["maxCurrent"], 60, 5)
    log(bool(follow), "evcc follows the ceiling (effective maximum current)", f"{evcc_lp(1).get('effectiveMaxCurrent')} A")

    # ---- leaving active mode gives the ORIGINAL ceiling back ----
    it.svc("select", "select_option", {"entity_id": "select.viertelstunden_wachter_betriebsart", "option": "observe"})
    back = it.wait_for(lambda: evcc_lp(1)["maxCurrent"] == 16, 120, 5)
    log(bool(back), "leaving active mode gives the original ceiling back (16 A)", f"{evcc_lp(1)['maxCurrent']} A")

    # ---- restart during an intervention: the original ceiling is found again ----
    it.svc("input_number", "set_value", {"entity_id": "input_number.hauslast_w", "value": 2000})
    it.svc("select", "select_option", {"entity_id": "select.viertelstunden_wachter_betriebsart", "option": "active"})
    it.wait_for(lambda: evcc_lp(1)["maxCurrent"] < 16, 300, 5)
    before = evcc_lp(1)["maxCurrent"]
    time.sleep(35)  # let the state be saved (it is saved a few seconds after a change)
    subprocess.run(["docker", "restart", it.CONTAINER], check=False, capture_output=True)
    it.wait_ready(240)
    it.wait_for(lambda: evcc_lp(1)["maxCurrent"] == 16, 240, 5)
    log(evcc_lp(1)["maxCurrent"] == 16, "restart during an intervention: the original ceiling is given back", f"before {before} A, after {evcc_lp(1)['maxCurrent']} A")

    # ---- the grid import from evcc: own sensor wins, evcc fills gaps, never an average ----
    def options(values):
        s, d = it.api("POST", "/api/config/config_entries/options/flow", {"handler": entry_id})
        if s != 200 or d.get("type") != "form":
            return None, f"init {s} {d}"
        base_opts = {"mains_voltage": 230, "max_reading_age_s": 120, "startup_mode": "restore", "evcc_backup": True}
        s, d = it.api("POST", f"/api/config/config_entries/options/flow/{d['flow_id']}", {**base_opts, **values})
        return (d if d.get("type") == "create_entry" else None), str(d.get("errors") or d.get("type"))

    def status_attr(key):
        st = it.state("sensor.viertelstunden_wachter_status")
        return (st or {}).get("attributes", {}).get(key)

    it.svc("select", "select_option", {"entity_id": "select.viertelstunden_wachter_betriebsart", "option": "observe"})
    res, err = options({})
    log(res is None and "grid_source_missing" in err, "without a sensor and without evcc the settings are refused", err)
    res, err = options({"evcc_site_url": "http://host.docker.internal:1"})
    log(res is None and "evcc_unreachable" in err, "an evcc address that does not answer is refused", err)
    res, err = options({"evcc_site_url": EVCC_FROM_HA})
    log(res is not None, "grid import only from evcc (no own sensor) is accepted", err)
    src = it.wait_for(lambda: status_attr("grid_source") == "evcc", 90, 5)
    log(bool(src) and val("sensor.viertelstunden_wachter_status") != "no_data", "the guard works with the grid import from evcc",
        f"source {status_attr('grid_source')}, evcc {status_attr('grid_evcc_kw')} kW, status {val('sensor.viertelstunden_wachter_status')}")

    # own sensor and evcc: the sensor wins; they differ clearly here (simulated house vs demo evcc): a note, no average
    res, err = options({"grid_power": "sensor.netzbezug", "evcc_site_url": EVCC_FROM_HA})
    log(res is not None, "own sensor plus evcc is accepted", err)
    src = it.wait_for(lambda: status_attr("grid_source") == "sensor", 90, 5)
    log(bool(src), "with both, the own sensor wins", f"source {status_attr('grid_source')}")
    differ = it.wait_for(lambda: status_attr("sources_differ") is True, 240, 10)
    log(bool(differ), "a clear difference of the two sources is shown (after two minutes)", f"sources_differ {status_attr('sources_differ')}")
    recent = " | ".join(status_attr("recent") or [])
    log("evcc" in recent, "the difference is written to the log once", recent[:200])

    # reserve: a sensor that stops updating gets too old; evcc takes over, and does not when the reserve is off
    res, err = options({"grid_power": "sensor.netzbezug_still", "evcc_site_url": EVCC_FROM_HA, "evcc_backup": True})
    log(res is not None, "reserve on, sensor that stops updating", err)
    reserve = it.wait_for(lambda: status_attr("grid_stale") is True and status_attr("grid_source") == "evcc", 240, 10)
    log(bool(reserve), "the stale sensor is replaced by evcc (reserve)", f"stale {status_attr('grid_stale')}, source {status_attr('grid_source')}")
    res, err = options({"grid_power": "sensor.netzbezug_still", "evcc_site_url": EVCC_FROM_HA, "evcc_backup": False})
    log(res is not None, "reserve off", err)
    nodata = it.wait_for(lambda: status_attr("grid_source") is None, 120, 10)
    log(bool(nodata), "with the reserve off a stale sensor means no data (as before)", f"source {status_attr('grid_source')}, status {val('sensor.viertelstunden_wachter_status')}")
    # the dashboard of the integration shows the card 'Sources compared' only with evcc, and it renders in Home Assistant
    res, err = options({"grid_power": "sensor.netzbezug", "evcc_site_url": EVCC_FROM_HA})
    s, d = it.api("POST", "/api/services/viertelstunden_waechter/create_dashboard?return_response", {})
    dash = (d or {}).get("service_response") or {}
    cards = [c for v in dash.get("views", []) for sec in v.get("sections", []) for c in sec.get("cards", []) if c.get("type") == "markdown"]
    src = [c for c in cards if "Quellen im Vergleich" in c["content"] or "Sources compared" in c["content"]]
    sc, body = it.api("POST", "/api/template", {"template": src[0]["content"]}) if src else (0, "")
    log(len(src) == 1 and sc == 200 and "svg" in str(body) and "Error" not in str(body)[:80], "with evcc the dashboard has the card Sources compared, and it renders",
        f"{len(src)} card(s), {sc}, {str(body)[:80]}")
    res, err = options({"grid_power": "sensor.netzbezug"})
    log(res is not None and it.wait_for(lambda: status_attr("grid_source") == "sensor", 90, 5), "back to the own sensor only", err)

    # ---- observe only per device, and the warning for a wallbox entered twice ----
    it.svc("input_boolean", "turn_on", {"entity_id": "input_boolean.auto_laedt"})
    it.svc("input_number", "set_value", {"entity_id": "input_number.wb_strom", "value": 16})
    twin = {"name": "Wallbox doppelt", "priority": 2, "power_entity": "sensor.wallbox_leistung", "current_entity": "input_number.wb_strom",
            "min_current": 6, "max_current": 16, "observe_only": True}
    res, err = it.flow_finish("/api/config/config_entries/subentries/flow", {"handler": [entry_id, "wallbox"]}, twin)
    log(res is not None, "a wallbox set to observe only is accepted", err)
    it.svc("input_number", "set_value", {"entity_id": "input_number.hauslast_w", "value": 2000})
    # observe mode: nothing is throttled, so both charge with the same power (in active mode the guard would lower the loadpoint)
    it.svc("select", "select_option", {"entity_id": "select.viertelstunden_wachter_betriebsart", "option": "observe"})
    evcc_post("/api/loadpoints/1/maxcurrent/16")
    twice = it.wait_for(lambda: status_attr("wallbox_twice"), 300, 10)
    log(bool(twice), "a wallbox and an evcc loadpoint with the same power are reported as probably the same wallbox", str(status_attr("wallbox_twice")))
    recent = " | ".join(status_attr("recent") or [])
    log("dieselbe Wallbox" in recent or "same wallbox" in recent, "the warning is written to the log", recent[:220])
    watched = it.wait_for(lambda: "Nur beobachten" in " | ".join(status_attr("recent") or []) or "Observe only" in " | ".join(status_attr("recent") or []), 300, 10)
    log(bool(watched), "the observed wallbox gets a note what would be done", " | ".join(status_attr("recent") or [])[:220])
    log(float(val("input_number.wb_strom")) == 16.0, "nothing is sent to the observed wallbox", f"{val('input_number.wb_strom')} A")
    it.svc("select", "select_option", {"entity_id": "select.viertelstunden_wachter_betriebsart", "option": "observe"})

    logs = subprocess.run(["docker", "logs", it.CONTAINER], capture_output=True, text=True).stdout
    errs = [ln for ln in logs.splitlines() if "viertelstunden_waechter" in ln and (" ERROR " in ln or "Traceback" in ln)]
    log(not errs, "no errors of the integration in the log", "; ".join(errs[:3]))
    evcc_post("/api/loadpoints/1/maxcurrent/16")
    evcc_post("/api/loadpoints/1/mode/smart")


if __name__ == "__main__":
    try:
        main()
    finally:
        fails = [ln for ok, ln in it.REPORT if not ok]
        print(f"\n===== RESULT: {len(it.REPORT) - len(fails)} of {len(it.REPORT)} checks passed =====")
        for ln in fails:
            print(ln)
        with open("tests/install/report_evcc.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(ln for _, ln in it.REPORT) + "\n")
        sys.exit(1 if fails else 0)
