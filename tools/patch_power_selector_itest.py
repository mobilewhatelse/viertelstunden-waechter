"""One-off: installation test for issue 1 (kept for the record).

The simulated grid sensor now has NO device class (as the template sensors in the issue), so the whole run proves that such a sensor works;
a sensor without a unit must be refused with a clear error; the grid power field must not filter by device class."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def rw(rel, fn):
    p = ROOT / rel
    s = p.read_text(encoding="utf-8", newline="")
    crlf = "\r\n" in s
    s = fn(s.replace("\r\n", "\n"))
    if crlf:
        s = s.replace("\n", "\r\n")
    p.write_text(s, encoding="utf-8", newline="")


def cfg(s):
    a = '''      - name: Netzbezug
        unique_id: netzbezug
        unit_of_measurement: W
        device_class: power
        state_class: measurement
'''
    b = '''      - name: Netzbezug
        unique_id: netzbezug
        unit_of_measurement: W
        state_class: measurement
'''
    assert s.count(a) == 1
    s = s.replace(a, b)
    c = '''      - name: Akku Ladestand
        unique_id: akku_soc
'''
    d = '''      - name: Netz ohne Einheit
        unique_id: netz_ohne_einheit
        state: "100"
      - name: Akku Ladestand
        unique_id: akku_soc
'''
    assert s.count(c) == 1
    return s.replace(c, d)


def test(s):
    a = '''    entry, err = flow_finish("/api/config/config_entries/flow", {"handler": "viertelstunden_waechter", "show_advanced_options": False},
                             {"name": "Viertelstunden-Wächter", "grid_power": "sensor.netzbezug", "limit_kw": 10.0, "margin_kw": 0.5})
'''
    b = '''    fields = {f.get("name"): f for f in (d.get("data_schema") or [])}
    sel = ((fields.get("grid_power") or {}).get("selector") or {}).get("entity") or {}
    log(bool(sel) and not sel.get("device_class") and "device_class" not in str(sel), "Netzbezug-Feld filtert nicht nach Geraeteklasse (Issue 1)", str(sel))
    s2, d2 = api("POST", f"/api/config/config_entries/flow/{d['flow_id']}", {"name": "Viertelstunden-Wächter", "grid_power": "sensor.netz_ohne_einheit", "limit_kw": 10.0, "margin_kw": 0.5})
    log(s2 == 200 and d2.get("type") == "form" and (d2.get("errors") or {}).get("grid_power") == "not_power", "Sensor ohne Einheit wird mit klarem Fehler abgelehnt", str(d2.get("errors")))
    api("DELETE", f"/api/config/config_entries/flow/{d['flow_id']}")
    entry, err = flow_finish("/api/config/config_entries/flow", {"handler": "viertelstunden_waechter", "show_advanced_options": False},
                             {"name": "Viertelstunden-Wächter", "grid_power": "sensor.netzbezug", "limit_kw": 10.0, "margin_kw": 0.5})
'''
    assert s.count(a) == 1
    return s.replace(a, b)


rw("tests/install/config/configuration.yaml", cfg)
rw("tests/install/itest.py", test)
print("ok")
