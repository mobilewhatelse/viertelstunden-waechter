"""One-off: evcc as a wallbox of the guard, dialog and texts (kept for the record)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "custom_components" / "viertelstunden_waechter"


def edit(name, pairs):
    p = PKG / name
    s = p.read_text(encoding="utf-8", newline="")
    crlf = "\r\n" in s
    s = s.replace("\r\n", "\n")
    for a, b in pairs:
        assert s.count(a) == 1, (name, a[:80], s.count(a))
        s = s.replace(a, b)
    if crlf:
        s = s.replace("\n", "\r\n")
    p.write_text(s, encoding="utf-8", newline="")


edit("config_flow.py", [
    ("from .engine import KIND_BATTERY, KIND_SCRIPT, KIND_SETTING, KIND_SWITCH, KIND_THROTTLE, KIND_VEHICLE, KIND_WALLBOX\n",
     "from .engine import KIND_BATTERY, KIND_EVCC, KIND_SCRIPT, KIND_SETTING, KIND_SWITCH, KIND_THROTTLE, KIND_VEHICLE, KIND_WALLBOX\n"
     "from .const import D_EVCC_LOADPOINT, D_EVCC_ONE_PHASE, D_EVCC_PASSWORD, D_EVCC_URL\n"
     "from .evcc import EvccAuthError, EvccClient, EvccError, parse_loadpoint\n"),
    ('1 if kind == KIND_WALLBOX else 5 if kind == KIND_SWITCH else 10', '1 if kind in (KIND_WALLBOX, KIND_EVCC) else 5 if kind == KIND_SWITCH else 10'),
    ('''    elif kind == KIND_WALLBOX:
        s[vol.Required(D_POWER, default=d.get(D_POWER, vol.UNDEFINED))] = _ent("sensor")''',
     '''    elif kind == KIND_EVCC:
        s[vol.Required(D_EVCC_URL, default=d.get(D_EVCC_URL, vol.UNDEFINED))] = TextSelector()
        s[vol.Required(D_EVCC_LOADPOINT, default=d.get(D_EVCC_LOADPOINT, 1))] = _num(1, 20)
        s[_opt(D_EVCC_PASSWORD, d)] = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
        s[vol.Required(D_MIN_CURRENT, default=d.get(D_MIN_CURRENT, 6))] = _num(6, 32, 1, "A")
        s[vol.Required(D_MAX_CURRENT, default=d.get(D_MAX_CURRENT, 16))] = _num(6, 32, 1, "A")
        s[vol.Required(D_EVCC_ONE_PHASE, default=bool(d.get(D_EVCC_ONE_PHASE, False)))] = BooleanSelector()
        s[_opt(D_POWER, d)] = _ent("sensor")
        s[_opt(D_ALLOW, d)] = _ent(ON_OFF_DOMAINS)
    elif kind == KIND_WALLBOX:
        s[vol.Required(D_POWER, default=d.get(D_POWER, vol.UNDEFINED))] = _ent("sensor")'''),
    ('''    if kind == KIND_WALLBOX:
        what = f"{int(d.get(D_MAX_CURRENT, 16))}→{int(d.get(D_MIN_CURRENT, 6))} A" + (", 1~" if d.get(D_ONE_PHASE) else "")''',
     '''    if kind == KIND_EVCC:
        what = (f"evcc #{int(d.get(D_EVCC_LOADPOINT, 1))} · {int(d.get(D_MAX_CURRENT, 16))}→{int(d.get(D_MIN_CURRENT, 6))} A"
                + (", 1~" if d.get(D_EVCC_ONE_PHASE) else ""))
    elif kind == KIND_WALLBOX:
        what = f"{int(d.get(D_MAX_CURRENT, 16))}→{int(d.get(D_MIN_CURRENT, 6))} A" + (", 1~" if d.get(D_ONE_PHASE) else "")'''),
    ('''            KIND_WALLBOX: WallboxFlow, KIND_SWITCH: SwitchFlow,''', '''            KIND_WALLBOX: WallboxFlow, KIND_EVCC: EvccFlow, KIND_SWITCH: SwitchFlow,'''),
    ('''            errors = unit_errors(self.hass.states.get, user_input, (D_POWER,)) or self._validate(user_input)
            if not errors:''', '''            errors = unit_errors(self.hass.states.get, user_input, (D_POWER,)) or self._validate(user_input)
            if not errors:
                errors = await self._validate_async(user_input)
            if not errors:'''),
    ('''                for k in (D_PRIORITY, D_MIN_CURRENT, D_MAX_CURRENT):''', '''                for k in (D_PRIORITY, D_MIN_CURRENT, D_MAX_CURRENT, D_EVCC_LOADPOINT):'''),
    ('''    def _validate(self, u: dict[str, Any]) -> dict[str, str]:
        return {}


class WallboxFlow(_DeviceFlow):''', '''    def _validate(self, u: dict[str, Any]) -> dict[str, str]:
        return {}

    async def _validate_async(self, u: dict[str, Any]) -> dict[str, str]:
        return {}


class EvccFlow(_DeviceFlow):
    """A loadpoint of evcc: the guard sets evcc's ceiling for the charging current (see evcc.py). Checks the connection when saving."""

    kind = KIND_EVCC

    def _validate(self, u: dict[str, Any]) -> dict[str, str]:
        if int(u.get(D_MIN_CURRENT, 6)) > int(u.get(D_MAX_CURRENT, 16)):
            return {D_MIN_CURRENT: "min_above_max"}
        return {}

    async def _validate_async(self, u: dict[str, Any]) -> dict[str, str]:
        client = EvccClient(async_get_clientsession(self.hass), str(u.get(D_EVCC_URL) or ""), u.get(D_EVCC_PASSWORD))
        try:
            state = await client.state()
        except EvccAuthError:
            return {D_EVCC_PASSWORD: "evcc_auth"}
        except EvccError:
            return {D_EVCC_URL: "evcc_unreachable"}
        if parse_loadpoint(state, int(float(u.get(D_EVCC_LOADPOINT) or 1))) is None:
            return {D_EVCC_LOADPOINT: "evcc_loadpoint"}
        return {}


class WallboxFlow(_DeviceFlow):'''),
])
s = (PKG / "config_flow.py").read_text(encoding="utf-8", newline="")
crlf = "\r\n" in s
s = s.replace("\r\n", "\n")
# selectors and the shared session
import re
m = re.search(r"from homeassistant\.helpers\.selector import \(\n(?:.*\n)*?\)\n", s)
assert m, "selector import not found"
block = m.group(0)
assert "TextSelectorConfig" not in block
new_block = block.replace("TextSelector,", "TextSelector, TextSelectorConfig, TextSelectorType,", 1) if "TextSelector," in block else block
assert new_block != block, "TextSelector not found in import"
s = s.replace(block, new_block)
s = s.replace("from homeassistant.core import callback\n", "from homeassistant.core import callback\nfrom homeassistant.helpers.aiohttp_client import async_get_clientsession\n", 1)
if crlf:
    s = s.replace("\n", "\r\n")
(PKG / "config_flow.py").write_text(s, encoding="utf-8", newline="")

# ---- texts (strings.json and the two translations) ----
EN = dict(
    entry_type="evcc loadpoint (wallbox)", add="Add evcc loadpoint", reconf="Reconfigure evcc loadpoint", title="evcc loadpoint",
    desc="The guard sets evcc's maximum charging current (a ceiling, evcc keeps regulating below it) and takes it back. Charging is never stopped. "
         "No other integration is needed, the address of evcc is enough.",
    data=dict(name="Name", priority="Priority", evcc_url="Address of evcc", evcc_loadpoint="Loadpoint number", evcc_password="Password of evcc",
              min_current="Minimum current", max_current="Maximum current", evcc_one_phase="May switch to 1 phase",
              power_entity="Charging power (optional)", allow_entity="Intervention only while"),
    desc_fields=dict(priority="1 = restricted first, 10 = only when nothing else helps.",
                     evcc_url="For example http://192.168.1.20:7070 (reachable from Home Assistant).",
                     evcc_loadpoint="1 = the first loadpoint in evcc.",
                     evcc_password="Only if evcc asks for a password (administrator password).",
                     max_current="The ceiling the guard gives back to evcc afterwards is the one evcc had before.",
                     evcc_one_phase="Only works if the charger can switch phases. Off = only throttled.",
                     power_entity="Optional sensor, for example from the evcc integration of the community. Without it the guard reads the power from evcc.",
                     allow_entity="Optional. Only while this entity is on."),
    errors=dict(evcc_unreachable="evcc cannot be reached at this address.", evcc_loadpoint="evcc has no loadpoint with this number.",
                evcc_auth="evcc asks for a password, or the password is wrong."),
)
DE = dict(
    entry_type="evcc-Ladepunkt (Wallbox)", add="evcc-Ladepunkt hinzufügen", reconf="evcc-Ladepunkt ändern", title="evcc-Ladepunkt",
    desc="Der Wächter setzt den maximalen Ladestrom von evcc (eine Obergrenze, darunter regelt evcc weiter) und gibt ihn zurück. Das Laden wird nie gestoppt. "
         "Es wird keine andere Integration gebraucht, die Adresse von evcc genügt.",
    data=dict(name="Name", priority="Priorität", evcc_url="Adresse von evcc", evcc_loadpoint="Nummer des Ladepunkts", evcc_password="Passwort von evcc",
              min_current="Mindeststrom", max_current="Höchststrom", evcc_one_phase="Darf auf 1 Phase umschalten",
              power_entity="Ladeleistung (optional)", allow_entity="Eingriff nur solange"),
    desc_fields=dict(priority="1 = wird zuerst eingeschränkt, 10 = nur wenn nichts anderes hilft.",
                     evcc_url="Zum Beispiel http://192.168.1.20:7070 (von Home Assistant aus erreichbar).",
                     evcc_loadpoint="1 = der erste Ladepunkt in evcc.",
                     evcc_password="Nur wenn evcc ein Passwort verlangt (Administrator-Passwort).",
                     max_current="Zurückgegeben wird die Obergrenze, die evcc vorher hatte.",
                     evcc_one_phase="Geht nur, wenn die Wallbox die Phasen umschalten kann. Aus = nur drosseln.",
                     power_entity="Optionaler Sensor, zum Beispiel aus der evcc-Integration der Community. Ohne ihn liest der Wächter die Leistung aus evcc.",
                     allow_entity="Optional. Nur solange diese Entität an ist."),
    errors=dict(evcc_unreachable="evcc ist unter dieser Adresse nicht erreichbar.", evcc_loadpoint="evcc hat keinen Ladepunkt mit dieser Nummer.",
                evcc_auth="evcc verlangt ein Passwort, oder das Passwort ist falsch."),
)
NOT_POWER = {
    "strings.json": "This sensor has no power unit (W, kW or MW). Add unit_of_measurement: W to the template sensor or choose another sensor.",
    "translations/en.json": "This sensor has no power unit (W, kW or MW). Add unit_of_measurement: W to the template sensor or choose another sensor.",
    "translations/de.json": "Dieser Sensor hat keine Leistungseinheit (W, kW oder MW). Ergänzen Sie beim Template-Sensor unit_of_measurement: W oder wählen Sie einen anderen Sensor.",
}
MIN_ABOVE_MAX = {"strings.json": "Minimum current is above maximum current.", "translations/en.json": "Minimum current is above maximum current.",
                 "translations/de.json": "Der Mindeststrom liegt über dem Höchststrom."}
for rel, L in (("strings.json", EN), ("translations/en.json", EN), ("translations/de.json", DE)):
    p = PKG / rel
    raw = p.read_text(encoding="utf-8", newline="")
    crlf = "\r\n" in raw
    d = json.loads(raw)
    step = {"title": L["title"], "description": L["desc"], "data": L["data"], "data_description": L["desc_fields"]}
    d["config_subentries"]["evcc"] = {
        "entry_type": L["entry_type"],
        "initiate_flow": {"user": L["add"], "reconfigure": L["reconf"]},
        "step": {"user": step, "reconfigure": step},
        "error": {**L["errors"], "min_above_max": MIN_ABOVE_MAX[rel], "not_power": NOT_POWER[rel]},
        "abort": {"reconfigure_successful": d["config_subentries"]["wallbox"].get("abort", {}).get("reconfigure_successful", "Done.")},
    }
    out = json.dumps(d, indent=2, ensure_ascii=False) + "\n"
    if crlf:
        out = out.replace("\n", "\r\n")
    p.write_text(out, encoding="utf-8", newline="")
print("ok")
