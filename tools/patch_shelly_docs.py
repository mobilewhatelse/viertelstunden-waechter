"""One-off: version 0.13.3 and the note on template sensors (e.g. built from the phases of a Shelly 3EM Pro) (kept for the record).

The wording is deliberate: it was NOT tested with a real Shelly; it was tested with an equivalent simulated template sensor without a
device class. 'Confirmed by a user' can be added once the reporter of issue 1 confirms it.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def edit(rel, pairs):
    p = ROOT / rel
    s = p.read_text(encoding="utf-8", newline="")
    crlf = "\r\n" in s
    s = s.replace("\r\n", "\n")
    for a, b in pairs:
        assert s.count(a) == 1, (rel, a[:80], s.count(a))
        s = s.replace(a, b)
    if crlf:
        s = s.replace("\n", "\r\n")
    p.write_text(s, encoding="utf-8", newline="")


edit("README.md", [(
    '''3. **A meter in the distribution board**, e.g. a 3-phase energy meter via its integration or **Modbus**.
''', '''3. **A meter in the distribution board**, e.g. a 3-phase energy meter via its integration or **Modbus**.
4. **A template sensor you build yourself**, for example from the three phase values of a **Shelly 3EM Pro** (the sum of the phases, its
   positive part as import). Any sensor with the unit W or kW works, **a device class is not needed**: the dialog checks the unit, not the
   class (see [issue 1](https://github.com/mobilewhatelse/viertelstunden-waechter/issues/1)). This setup is covered by the installation test
   with an equivalent simulated sensor; it has not been tested with a real Shelly device here.
''')])
edit("docs/ANLEITUNG.md", [(
    '''| **Messgerät im Verteiler** (3-Phasen-Energiezähler, Hutschienenzähler) | eigene Integration oder Modbus | 1–5 s | gut |
''', '''| **Messgerät im Verteiler** (3-Phasen-Energiezähler, Hutschienenzähler) | eigene Integration oder Modbus | 1–5 s | gut |
| **Selbst gebauter Template-Sensor**, z. B. aus den drei Phasenwerten eines **Shelly 3EM Pro** (Summe der Phasen, der positive Teil als Bezug) | Template in der Konfiguration; jeder Sensor mit der Einheit W oder kW geht, **eine Geräteklasse ist nicht nötig** (geprüft wird die Einheit) | wie der Shelly | gut; im Installationstest mit einem gleichwertigen simulierten Sensor abgedeckt, mit einem echten Shelly hier nicht getestet |
''')])
edit("CHANGELOG.md", [(
    '''## Unreleased

- **Fix (issue 1):** grid power, grid energy and the power sensor of a device can be **any sensor**, also a template sensor with the unit
  `W` but without `device_class: power`. Before, such sensors were missing from the list. Instead of the device class the dialog now checks
  the **unit** when saving (W, kW, MW for power; Wh, kWh, MWh for energy) and says what to add if it is missing.

- Roadmap''', '''## Unreleased

- Roadmap''')])
edit("CHANGELOG.md", [(
    '''## 0.13.2 - 2026-11-03
''', '''## 0.13.3 - 2026-11-08

- **Fix (issue 1):** grid power, grid energy and the power sensor of a device can be **any sensor**, also a template sensor with the unit
  `W` but without `device_class: power` (for example one built from the three phases of a Shelly 3EM Pro). Before, such sensors were missing
  from the list. Instead of the device class the dialog now checks the **unit** when saving (W, kW, MW for power; Wh, kWh, MWh for energy)
  and says what to add if it is missing. Covered by the installation test with an equivalent simulated sensor; not tested with a real Shelly
  device here.

Deutsch: Netzbezug, Bezugszähler und die Leistungssensoren der Geräte können **jeder Sensor** sein, auch ein Template-Sensor mit der Einheit W
ohne Geräteklasse (z. B. aus den drei Phasen eines Shelly 3EM Pro). Statt der Geräteklasse prüft der Dialog beim Speichern die Einheit.

## 0.13.2 - 2026-11-03
''')])
m = ROOT / "custom_components" / "viertelstunden_waechter" / "manifest.json"
raw = m.read_text(encoding="utf-8", newline="")
d = json.loads(raw)
d["version"] = "0.13.3"
out = json.dumps(d, indent=2, ensure_ascii=False) + "\n"
if "\r\n" in raw:
    out = out.replace("\n", "\r\n")
m.write_text(out, encoding="utf-8", newline="")
print("ok")
