"""Install test for a wallbox whose charging current is a list (select '6 A' ... '16 A', like the Anker SOLIX V1), since 0.14.3.
The test house has a list `input_select.anker_max_ev_ladestrom`, a power sensor that follows it, and the grid import adds it.

Run:  python tests/install/itest_liste.py   (Docker needed; creates and removes container vw-liste on port 18129)"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))
import itest as it  # noqa: E402

NAME, PORT, RUN = "vw-liste", 18129, HERE / "run_liste"
it.BASE = f"http://localhost:{PORT}"
it.CONTAINER = NAME
SEL = "input_select.anker_max_ev_ladestrom"
OPTIONS = ["6 A", "8 A", "10 A", "12 A", "14 A", "16 A"]
results: list[bool] = []


def log(ok: bool, what: str, detail: str = "") -> None:
    results.append(bool(ok))
    print(("PASS  " if ok else "FAIL  ") + what + (f"  [{detail}]" if detail else ""), flush=True)


def val(eid: str) -> str | None:
    return (it.state(eid) or {}).get("state")


def main() -> int:
    subprocess.run(["docker", "rm", "-f", NAME], capture_output=True)
    if RUN.exists():
        shutil.rmtree(RUN)
    shutil.copytree(HERE / "config", RUN)
    shutil.copytree(REPO / "custom_components" / "viertelstunden_waechter", RUN / "custom_components" / "viertelstunden_waechter")
    subprocess.run(["docker", "run", "-d", "--name", NAME, "-p", f"{PORT}:8123", "-v", f"{RUN}:/config", "-e", "TZ=Europe/Vienna",
                    "ghcr.io/home-assistant/home-assistant:stable"], capture_output=True)
    log(it.wait_ready(300), "HA starts")
    ok, err = it.onboard()
    log(ok, "onboarding", err)
    it.wait_for(lambda: val("sensor.netzbezug") not in (None, "unknown", "unavailable"), 120)
    it.svc("input_boolean", "turn_off", {"entity_id": "input_boolean.pool_pumpe"})
    _, err = it.flow_finish("/api/config/config_entries/flow", {"handler": "viertelstunden_waechter"},
                            {"name": "Viertelstunden-Wächter", "grid_power": "sensor.netzbezug", "limit_kw": 10.0, "margin_kw": 0.5})
    eid = it.api("GET", "/api/config/config_entries/entry?domain=viertelstunden_waechter")[1][0]["entry_id"]
    res, err = it.flow_finish("/api/config/config_entries/subentries/flow", {"handler": [eid, "wallbox"]},
                              {"name": "Anker SOLIX V1", "priority": 1, "power_entity": "sensor.anker_leistung", "current_entity": SEL,
                               "min_current": 6, "max_current": 16})
    log(bool(res), "the wallbox dialog takes a list (select) as charging current", str(err or ""))
    time.sleep(10)

    # a peak: house 5 kW + wallbox 16 A (11 kW) -> about 16 kW over a limit of 10 kW
    it.svc("input_boolean", "turn_on", {"entity_id": "input_boolean.anker_laedt"})
    it.svc("input_number", "set_value", {"entity_id": "input_number.hauslast_w", "value": 5000})
    it.svc("select", "select_option", {"entity_id": "select.viertelstunden_wachter_betriebsart", "option": "active"})
    low = it.wait_for(lambda: val(SEL) not in (None, "16 A"), 960, 10)
    log(bool(low), "Active: the guard picks a lower entry of the list", str(val(SEL)))
    seen = set()
    for _ in range(18):
        seen.add(val(SEL))
        time.sleep(10)
    log(seen <= set(OPTIONS), "only entries of the list are set (no '7 A' or numbers)", str(sorted(seen)))
    log(val(SEL) in ("6 A", "8 A"), "the wallbox ends on a low entry while the house needs 5 kW", str(val(SEL)))
    st = it.state("sensor.viertelstunden_wachter_status")
    today = "\n".join((st or {}).get("attributes", {}).get("today", []))
    log("Anker SOLIX V1" in today and "->" in today, "the log names the wallbox and the step", today.splitlines()[-1][:120] if today else "")
    log("nicht umgesetzt" not in today and "not carried out" not in today, "no 'not carried out' (the list follows)")

    # room again: the guard raises entry by entry, as far as it fits (16 A alone is 11 kW, above the limit of 10 kW;
    # with 0.4 kW house 12 A = 8.3 kW is the highest entry under the target of 9.5 kW)
    it.svc("input_number", "set_value", {"entity_id": "input_number.hauslast_w", "value": 400})
    up = it.wait_for(lambda: val(SEL) == "12 A", 900, 10)
    log(bool(up), "with room again the list goes up to the highest entry that fits (12 A)", str(val(SEL)))
    time.sleep(120)
    log(val(SEL) == "12 A", "it does not go to 14 A, which would be above the target", str(val(SEL)))
    # charging ends: the guard gives the original entry back
    it.svc("input_boolean", "turn_off", {"entity_id": "input_boolean.anker_laedt"})
    back = it.wait_for(lambda: val(SEL) == "16 A", 300, 10)
    log(bool(back), "after charging the original entry 16 A is back", str(val(SEL)))

    logs = subprocess.run(["docker", "logs", NAME], capture_output=True, text=True, encoding="utf-8", errors="replace")
    bad = [line for line in (logs.stdout + logs.stderr).splitlines()
           if "viertelstunden" in line.lower() and ("ERROR" in line or "Traceback" in line or "Exception" in line)]
    log(not bad, "no errors of the guard in the log", bad[0][:200] if bad else "")
    subprocess.run(["docker", "rm", "-f", NAME], capture_output=True)
    print(f"\nERGEBNIS: {sum(results)} von {len(results)} Pruefungen bestanden (Wallbox mit Auswahlliste)", flush=True)
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
