"""The guard with an evcc that has an admin PASSWORD, in ONE fresh Home Assistant.

Needs a real evcc (the demo refuses a password) with tests/install/evcc_password/evcc.yaml:
  docker run -d --name evcc-pw -p 17071:7070 -v <repo>/tests/install/evcc_password/evcc.yaml:/etc/evcc.yaml evcc/evcc:latest evcc -c /etc/evcc.yaml
and the Home Assistant test container `vw-evcc-pw` with tests/install/config_evcc on port 18132 with
`--add-host=host.docker.internal:host-gateway` (the demo evcc on 17070 also runs, the test house reads it). The test sets the password
itself. Checks: a wrong password is refused (settings and loadpoint), the right one accepted, the grid import is read and the ceiling
is written with the password set, the password shows nowhere. Takes about ten to twenty minutes (real quarter hours).
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import itest as it  # noqa: E402  (the helpers of the single test)

it.BASE = "http://localhost:18132"
it.CONTAINER = "vw-evcc-pw"
EVCC_LOCAL = "http://localhost:17071"
EVCC_FROM_HA = "http://host.docker.internal:17071"
PASSWORD = "Pw-only-for-this-test-7"


def log(ok, name, detail=""):
    it.log(ok, name, detail)


def evcc(method, path, body=None):
    req = urllib.request.Request(EVCC_LOCAL + path, method=method, data=json.dumps(body).encode() if body is not None else b"",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


def lp1():
    s, body = evcc("GET", "/api/state")
    try:
        d = json.loads(body)
        return (d.get("result", d).get("loadpoints") or [{}])[0]
    except ValueError:
        return {}


def val(eid):
    s = it.state(eid)
    return s["state"] if s else None


def status_attr(key):
    return ((it.state("sensor.viertelstunden_wachter_status") or {}).get("attributes") or {}).get(key)


def main():
    # ---------- evcc with a password, the car charging at loadpoint 1 ----------
    ok = it.wait_for(lambda: evcc("GET", "/api/state")[0] == 200, 90, step=3)
    s, _ = evcc("PUT", "/api/auth/password", {"current": "", "new": PASSWORD})
    s_cfg, _ = evcc("GET", "/api/config/site")
    log(bool(ok) and s in (200, 201, 202, 204) and s_cfg == 401, "evcc runs and has an admin password (its settings want a login)",
        f"set {s}, settings without login {s_cfg}")
    evcc("POST", "/api/loadpoints/1/maxcurrent/16")
    evcc("POST", "/api/loadpoints/1/mode/now")

    if not it.wait_ready():
        log(False, "Home Assistant starts")
        return
    ok, msg = it.onboard()
    log(ok, "test user and token created", msg)
    if not ok:
        return
    it.wait_for(lambda: it.state("sensor.netzbezug") and it.state("sensor.netzbezug")["state"] not in ("unknown", "unavailable"), 120)
    entry, err = it.flow_finish("/api/config/config_entries/flow", {"handler": "viertelstunden_waechter", "show_advanced_options": False},
                                {"name": "Viertelstunden-Wächter", "grid_power": "sensor.netzbezug", "limit_kw": 10.0, "margin_kw": 0.5})
    log(entry is not None, "guard set up", err)
    if not entry:
        return
    entry_id = it.api("GET", "/api/config/config_entries/entry?domain=viertelstunden_waechter")[1][0]["entry_id"]

    # ---------- the settings: evcc for the grid import, a wrong password is refused ----------
    def options(values):
        s, d = it.api("POST", "/api/config/config_entries/options/flow", {"handler": entry_id})
        if s != 200 or d.get("type") != "form":
            return None, f"init {s} {d}"
        base = {"mains_voltage": 230, "max_reading_age_s": 120, "startup_mode": "restore", "evcc_backup": True, "grid_power": "sensor.netzbezug"}
        s, d = it.api("POST", f"/api/config/config_entries/options/flow/{d['flow_id']}", {**base, **values})
        return (d if d.get("type") == "create_entry" else None), str(d.get("errors") or d.get("type"))

    res, err = options({"evcc_site_url": EVCC_FROM_HA, "evcc_site_password": "wrong"})
    log(res is None and "evcc_auth" in err, "settings: a wrong evcc password is refused", err)
    res, err = options({"evcc_site_url": EVCC_FROM_HA, "evcc_site_password": PASSWORD})
    log(res is not None, "settings: the right password is accepted", err)
    seen = it.wait_for(lambda: status_attr("grid_evcc_kw") is not None, 120, 5)
    log(bool(seen), "the grid import of evcc is read with the password set", f"evcc {status_attr('grid_evcc_kw')} kW, source {status_attr('grid_source')}")

    # ---------- the loadpoint dialog: a wrong password is refused ----------
    base = {"name": "Carport", "priority": 1, "evcc_url": EVCC_FROM_HA, "evcc_loadpoint": 1, "min_current": 6, "max_current": 16, "evcc_one_phase": False}
    s, d = it.api("POST", "/api/config/config_entries/subentries/flow", {"handler": [entry_id, "evcc"]})
    fid = d.get("flow_id")
    s, d2 = it.api("POST", f"/api/config/config_entries/subentries/flow/{fid}", {**base, "evcc_password": "wrong"})
    log(s == 200 and (d2.get("errors") or {}).get("evcc_password") == "evcc_auth", "loadpoint: a wrong evcc password is refused", str(d2.get("errors")))
    it.api("DELETE", f"/api/config/config_entries/subentries/flow/{fid}")
    res, err = it.flow_finish("/api/config/config_entries/subentries/flow", {"handler": [entry_id, "evcc"]}, {**base, "evcc_password": PASSWORD, "power_entity": "sensor.evcc_demo_leistung"})
    log(res is not None, "loadpoint: the right password is accepted, the evcc loadpoint is added", err)
    if res is None:
        return
    time.sleep(15)

    # ---------- active: the ceiling is written into the evcc with a password ----------
    it.svc("switch", "turn_off", {"entity_id": "switch.viertelstunden_wachter_bereits_erreichte_spitze_nutzen"})
    it.svc("input_number", "set_value", {"entity_id": "input_number.hauslast_w", "value": 12000})
    it.svc("select", "select_option", {"entity_id": "select.viertelstunden_wachter_betriebsart", "option": "active"})
    low = it.wait_for(lambda: (lp1().get("maxCurrent") or 16) < 16, 960, 10)
    log(bool(low), "active: the guard lowers the ceiling of the evcc with a password", f"{lp1().get('maxCurrent')} A, power {lp1().get('chargePower')} W, charging {lp1().get('charging')}, status {val('sensor.viertelstunden_wachter_status')}, grid {val('sensor.netzbezug')}, recent {(status_attr('recent') or [])[:3]}")
    it.svc("select", "select_option", {"entity_id": "select.viertelstunden_wachter_betriebsart", "option": "observe"})
    back = it.wait_for(lambda: lp1().get("maxCurrent") == 16, 120, 5)
    log(bool(back), "leaving active mode gives the ceiling back (16 A)", f"{lp1().get('maxCurrent')} A")
    it.svc("input_number", "set_value", {"entity_id": "input_number.hauslast_w", "value": 500})

    # ---------- the password shows nowhere ----------
    s, states = it.api("GET", "/api/states")
    log(s == 200 and PASSWORD not in json.dumps(states), "the password is in no state or attribute")
    logs = subprocess.run(["docker", "logs", it.CONTAINER], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace").stdout
    log(PASSWORD not in logs, "the password is not in the log")
    errs = [ln for ln in logs.splitlines() if "viertelstunden_waechter" in ln and (" ERROR " in ln or "Traceback" in ln)]
    log(not errs, "no errors of the integration in the log", "; ".join(errs[:3]))


if __name__ == "__main__":
    try:
        main()
    finally:
        fails = [ln for ok, ln in it.REPORT if not ok]
        print(f"\n===== RESULT: {len(it.REPORT) - len(fails)} of {len(it.REPORT)} checks passed =====")
        for ln in fails:
            print(ln)
        with open("tests/install/report_evcc_password.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(ln for _, ln in it.REPORT) + "\n")
        sys.exit(1 if fails else 0)
