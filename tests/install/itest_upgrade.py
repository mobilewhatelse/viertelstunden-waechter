"""Upgrade test: a test HA set up with an older release (by default each of the last three releases in turn), then the working copy put in its place and HA restarted.
Checks that settings, devices and the mode survive, that nothing errors in the log, and that the hint for devices on
'Observe only' in the mode 'Active' appears after the update and its repair really switches the setting off.

The code is replaced completely by an update, the stored data (settings, devices, entity ids, learned values) is not:
the new code has to take what any of the older releases stored.

Run:  python tests/install/itest_upgrade.py [old tag ...]   (Docker needed; uses port 18128, container vw-upgrade)
Rule: before every release the update from each of the last three releases has to pass."""

from __future__ import annotations

import io
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))
import itest as it  # noqa: E402

NAME, PORT, RUN = "vw-upgrade", 18128, HERE / "run_upgrade"
it.BASE = f"http://localhost:{PORT}"
it.CONTAINER = NAME
COMP = "custom_components/viertelstunden_waechter"
results: list[tuple[bool, str, str]] = []


def log(ok: bool, what: str, detail: str = "") -> None:
    results.append((bool(ok), what, detail))
    print(("PASS  " if ok else "FAIL  ") + what + (f"  [{detail}]" if detail else ""), flush=True)


def docker(*args: str) -> str:
    return subprocess.run(["docker", *args], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout


def put_component(ref: str | None) -> None:
    target = RUN / COMP
    if target.exists():
        shutil.rmtree(target)
    if ref is None:
        shutil.copytree(REPO / COMP, target)
        return
    data = subprocess.run(["git", "-C", str(REPO), "archive", "--format=tar", ref, COMP], capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(RUN, filter="data")


def manifest_version() -> str:
    import json
    return json.loads((RUN / COMP / "manifest.json").read_text(encoding="utf-8"))["version"]


def last_releases(n: int = 3) -> list[str]:
    import json
    tags = subprocess.run(["git", "-C", str(REPO), "tag", "--sort=-v:refname", "--list", "v*"], capture_output=True, text=True).stdout.split()
    current = "v" + json.loads((REPO / COMP / "manifest.json").read_text(encoding="utf-8"))["version"]
    return [t for t in tags if t != current][:n]


def upgrade_from(OLD: str) -> None:
    docker("rm", "-f", NAME)
    if RUN.exists():
        shutil.rmtree(RUN)
    shutil.copytree(HERE / "config", RUN)
    put_component(OLD)
    old_version = manifest_version()
    docker("run", "-d", "--name", NAME, "-p", f"{PORT}:8123", "-v", f"{RUN}:/config", "-e", "TZ=Europe/Vienna",
           "ghcr.io/home-assistant/home-assistant:stable")
    log(it.wait_ready(300), f"old version {old_version} ({OLD}) starts")
    ok, err = it.onboard()
    log(ok, "onboarding", err)
    it.wait_for(lambda: (it.state("sensor.netzbezug") or {}).get("state") not in (None, "unknown", "unavailable"), 120)
    _, err = it.flow_finish("/api/config/config_entries/flow", {"handler": "viertelstunden_waechter"},
                            {"name": "Viertelstunden-Wächter", "grid_power": "sensor.netzbezug", "limit_kw": 10.0, "margin_kw": 0.5})
    eid = it.api("GET", "/api/config/config_entries/entry?domain=viertelstunden_waechter")[1][0]["entry_id"]
    res, err = it.flow_finish("/api/config/config_entries/subentries/flow", {"handler": [eid, "wallbox"]},
                              {"name": "Wallbox", "priority": 1, "power_entity": "sensor.wallbox_leistung",
                               "current_entity": "input_number.wb_strom", "min_current": 6, "max_current": 16, "observe_only": True})
    log(bool(res), "old version: wallbox set up (with 'Observe only' where the version knows it)", str(err or ""))
    time.sleep(10)
    it.svc("select", "select_option", {"entity_id": "select.viertelstunden_wachter_betriebsart", "option": "active"})
    time.sleep(5)
    log((it.state("select.viertelstunden_wachter_betriebsart") or {}).get("state") == "active", "old version: mode 'Active'")
    had_observe = "beobachten" in it.ws_session()[0]({"type": "config_entries/subentries/list", "entry_id": eid})[0]["result"][0]["title"]
    entities_before = sorted(e["entity_id"] for e in it.ws_session()[0]({"type": "config/entity_registry/list"})[0]["result"]
                             if e["platform"] == "viertelstunden_waechter")

    # ---------- update: stop, new files, start (as HACS does it) ----------
    docker("stop", "-t", "120", NAME)   # time to write the last states, as a normal restart does
    put_component(None)
    new_version = manifest_version()
    docker("start", NAME)
    log(it.wait_ready(300), f"after the update to {new_version} HA starts")
    it.wait_for(lambda: (it.state("select.viertelstunden_wachter_betriebsart") or {}).get("state") not in (None, "unknown", "unavailable"), 120)
    time.sleep(10)
    call, ws = it.ws_session()
    entry = it.api("GET", "/api/config/config_entries/entry?domain=viertelstunden_waechter")[1][0]
    log(entry["state"] == "loaded", "the guard loads after the update", entry["state"])
    log((it.state("select.viertelstunden_wachter_betriebsart") or {}).get("state") == "active", "mode stays 'Active'")
    entities_after = sorted(e["entity_id"] for e in call({"type": "config/entity_registry/list"})[0]["result"]
                            if e["platform"] == "viertelstunden_waechter")
    missing = sorted(set(entities_before) - set(entities_after))
    log(not missing, "no entity lost", ", ".join(missing))
    subs = call({"type": "config_entries/subentries/list", "entry_id": eid})[0]["result"]
    log(len(subs) == 1 and "Wallbox" in subs[0]["title"], "the wallbox is still there", str([s["title"] for s in subs]))

    def issues():
        return [i["issue_id"] for i in call({"type": "repairs/list_issues"})[0]["result"]["issues"] if i["domain"] == "viertelstunden_waechter"]

    if not had_observe:   # the old version did not know 'Observe only' per device (before 0.14.0): nothing to hint at
        log("observe_only_active" not in issues() and "beobachten" not in subs[0]["title"],
            "old version without 'Observe only': no hint, the wallbox acts", f"{subs[0]['title']} {issues()}")
        ws.close()
        check_log(OLD)
        return
    log("observe_only_active" in issues(), "hint under Repairs: 'Active' with the wallbox on 'Observe only'", str(issues()))
    s, d = it.api("POST", "/api/repairs/issues/fix", {"handler": "viertelstunden_waechter", "issue_id": "observe_only_active"})
    log(s == 200 and "Wallbox" in str(d.get("description_placeholders")), "the repair dialog names the wallbox", str(d)[:150])
    s, d = it.api("POST", f"/api/repairs/issues/fix/{d.get('flow_id')}", {})
    log(s == 200 and d.get("type") == "create_entry", "confirm", str(d)[:120])
    ok = it.wait_for(lambda: "observe_only_active" not in issues() and "beobachten" not in
                     call({"type": "config_entries/subentries/list", "entry_id": eid})[0]["result"][0]["title"], 60)
    stored = docker("exec", NAME, "cat", "/config/.storage/core.config_entries")
    log(ok and '"observe_only":false' in stored.replace(" ", ""), "after the repair the wallbox is no longer on 'Observe only'",
        call({"type": "config_entries/subentries/list", "entry_id": eid})[0]["result"][0]["title"])
    ws.close()
    check_log(OLD)


def check_log(old: str) -> None:
    logs = subprocess.run(["docker", "logs", NAME], capture_output=True, text=True, encoding="utf-8", errors="replace")
    bad = [line for line in (logs.stdout + logs.stderr).splitlines()
           if "viertelstunden_waechter" in line and ("ERROR" in line or "Error importing" in line or "Traceback" in line)]
    log(not bad, f"{old}: no errors of the guard in the log", bad[0][:200] if bad else "")
    docker("rm", "-f", NAME)


def main() -> int:
    olds = sys.argv[1:] or last_releases()
    for old in olds:
        print(f"\n===== update from {old} =====", flush=True)
        try:
            upgrade_from(old)
        except Exception as exc:  # one broken run must not hide the others
            log(False, f"{old}: run broke off", f"{type(exc).__name__}: {exc}")
    passed = sum(1 for ok, _, _ in results if ok)
    print(f"\nERGEBNIS: {passed} von {len(results)} Pruefungen bestanden (Update von {', '.join(olds)})", flush=True)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
