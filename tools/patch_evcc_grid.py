"""One-off: the grid import can also come from evcc (own sensor wins, evcc fills gaps, differences are shown, not averaged) (kept for the record).

Rule (agreed 2026-11-09): the sensor the user entered is used. evcc is used when no sensor is entered, or as a reserve (switch, default on)
when the sensor is missing or stale. If both are fresh and differ clearly for a while, a note is written once; the guard keeps the sensor.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "custom_components" / "viertelstunden_waechter"


def edit(path, pairs):
    p = path if isinstance(path, Path) else PKG / path
    s = p.read_text(encoding="utf-8", newline="")
    crlf = "\r\n" in s
    s = s.replace("\r\n", "\n")
    for a, b in pairs:
        assert s.count(a) == 1, (p.name, a[:80], s.count(a))
        s = s.replace(a, b)
    if crlf:
        s = s.replace("\n", "\r\n")
    p.write_text(s, encoding="utf-8", newline="")


# ---- pure decisions (evcc.py) ----
s = (PKG / "evcc.py").read_text(encoding="utf-8", newline="")
crlf = "\r\n" in s
s = s.replace("\r\n", "\n")
s += '''

# ---- the grid import from evcc, and what to do with two sources ----

SOURCES_DIFFER_ABS_KW = 0.3      # both values differ by more than this ...
SOURCES_DIFFER_REL = 0.15        # ... and by more than this share of the larger one
SOURCES_DIFFER_AFTER_S = 120.0   # ... for this long: a note is written (once per episode)


def parse_grid_kw(state: dict[str, Any] | None) -> float | None:
    """The grid power evcc reports, in kW (positive = import, negative = export), or None if evcc has no grid meter."""
    grid = (state or {}).get("grid")
    if not isinstance(grid, dict):
        return None
    p = _num(grid.get("power"))
    return p / 1000.0 if p is not None else None


def choose_grid(sensor_kw: float | None, evcc_kw: float | None, sensor_configured: bool, backup: bool) -> tuple[float | None, str | None]:
    """(value in kW, source). The entered sensor wins; evcc counts when no sensor is entered, or as a reserve (`backup`) when the
    sensor has no usable value. Never an average of the two."""
    if sensor_kw is not None:
        return sensor_kw, "sensor"
    if evcc_kw is not None and (not sensor_configured or backup):
        return evcc_kw, "evcc"
    return None, None


def sources_differ(a_kw: float | None, b_kw: float | None) -> bool:
    """True if two readings of the same thing differ clearly (absolute and relative); a missing reading is no difference."""
    if a_kw is None or b_kw is None:
        return False
    diff = abs(a_kw - b_kw)
    return diff > SOURCES_DIFFER_ABS_KW and diff > SOURCES_DIFFER_REL * max(abs(a_kw), abs(b_kw))
'''
if crlf:
    s = s.replace("\n", "\r\n")
(PKG / "evcc.py").write_text(s, encoding="utf-8", newline="")

# ---- constants ----
edit("const.py", [(
    'CONF_GRID_ENERGY = "grid_energy"',
    'CONF_EVCC_URL = "evcc_site_url"          # optional: evcc as source of the grid import (own sensor wins)\n'
    'CONF_EVCC_PASSWORD = "evcc_site_password"\n'
    'CONF_EVCC_BACKUP = "evcc_backup"        # evcc takes over while the grid sensor has no usable value (default on)\n'
    'CONF_GRID_ENERGY = "grid_energy"',
)])

# ---- texts of the log lines ----
msgs = (PKG / "messages.py").read_text(encoding="utf-8", newline="")
crlf = "\r\n" in msgs
msgs = msgs.replace("\r\n", "\n")
de_anchor = '        "ahead": "Vorausschauend ({why}): {text}",\n'
assert msgs.count(de_anchor) == 1
msgs = msgs.replace(de_anchor, de_anchor +
    '        "grid_differ": "Netzbezug: Ihr Sensor zeigt {a:.1f} kW, evcc zeigt {b:.1f} kW. Der Wächter regelt mit Ihrem Sensor.",\n'
    '        "grid_backup_on": "Netzbezug: Ihr Sensor liefert nichts Brauchbares, der Wächter nimmt vorübergehend den Wert von evcc ({b:.1f} kW).",\n'
    '        "grid_backup_off": "Netzbezug: Ihr Sensor liefert wieder, der Wächter regelt wieder damit.",\n')
import re
m = re.search(r'    "en": \{\n(?:.*\n)*?        "ahead": ".*",\n', msgs)
assert m, "english block not found"
en_line = m.group(0).splitlines()[-1] + "\n"
msgs = msgs.replace(en_line, en_line +
    '        "grid_differ": "Grid import: your sensor shows {a:.1f} kW, evcc shows {b:.1f} kW. The guard works with your sensor.",\n'
    '        "grid_backup_on": "Grid import: your sensor has no usable value, the guard temporarily uses the value from evcc ({b:.1f} kW).",\n'
    '        "grid_backup_off": "Grid import: your sensor is delivering again, the guard works with it again.",\n', 1)
if crlf:
    msgs = msgs.replace("\n", "\r\n")
(PKG / "messages.py").write_text(msgs, encoding="utf-8", newline="")

# ---- coordinator ----
edit("coordinator.py", [
    ("from .const import D_EVCC_LOADPOINT, D_EVCC_ONE_PHASE, D_EVCC_PASSWORD, D_EVCC_URL\n",
     "from .const import CONF_EVCC_BACKUP, CONF_EVCC_PASSWORD, CONF_EVCC_URL, D_EVCC_LOADPOINT, D_EVCC_ONE_PHASE, D_EVCC_PASSWORD, D_EVCC_URL\n"),
    ("from .evcc import EvccClient, parse_loadpoint, target_ceiling, virtual_current\n",
     "from .evcc import (SOURCES_DIFFER_AFTER_S, EvccClient, choose_grid, parse_grid_kw, parse_loadpoint, sources_differ, target_ceiling,\n"
     "                   virtual_current)\n"),
    ('''        self.grid_stale = False              # True: the reading is older than allowed and counts as missing
''', '''        self.grid_stale = False              # True: the reading is older than allowed and counts as missing
        self.grid_source: str | None = None  # "sensor" or "evcc": where the grid import of this cycle came from
        self.grid_evcc_kw: float | None = None  # what evcc reports (None = not asked or no grid meter there)
        self.sources_differ = False          # sensor and evcc differ clearly (shown, never averaged)
        self._diff_since: datetime | None = None
        self._diff_noted = False
        self._on_backup = False
'''),
    ('''        eid = self.cfg.get(CONF_GRID_POWER)
        grid = self._power_kw(eid)
        st = self._state(eid)
        self.grid_age, self.grid_stale = None, False
        if grid is None or st is None:
            return grid
        stamp = max(st.last_updated, getattr(st, "last_reported", st.last_updated))
        self.grid_age = round(max(0.0, (now - stamp).total_seconds()), 1)
        max_age = float(self.cfg.get(CONF_MAX_AGE, DEFAULT_MAX_AGE_S))
        if max_age > 0 and self.grid_age > max_age:
            self.grid_stale = True
            return None
        return grid
''', '''        eid = self.cfg.get(CONF_GRID_POWER)
        grid = self._power_kw(eid) if eid else None
        st = self._state(eid) if eid else None
        self.grid_age, self.grid_stale = None, False
        if grid is not None and st is not None:
            stamp = max(st.last_updated, getattr(st, "last_reported", st.last_updated))
            self.grid_age = round(max(0.0, (now - stamp).total_seconds()), 1)
            max_age = float(self.cfg.get(CONF_MAX_AGE, DEFAULT_MAX_AGE_S))
            if max_age > 0 and self.grid_age > max_age:
                self.grid_stale = True
                grid = None
        # the sensor the user entered wins; evcc fills the gap (no sensor entered, or reserve while the sensor has nothing usable)
        kw, source = choose_grid(grid, self.grid_evcc_kw, bool(eid), bool(self.cfg.get(CONF_EVCC_BACKUP, True)))
        self.grid_source = source
        self._watch_sources(grid, source, now)
        return kw

    def _watch_sources(self, sensor_kw: float | None, source: str | None, now: datetime) -> None:
        """Say it once when the reserve takes over or gives back, and once per episode when sensor and evcc differ clearly."""
        if source == "evcc" and self.cfg.get(CONF_GRID_POWER) and not self._on_backup:
            self._on_backup = True
            self._log(Action("", "log", None, self.t("grid_backup_on", b=self.grid_evcc_kw or 0.0), False), False)
        elif source == "sensor" and self._on_backup:
            self._on_backup = False
            self._log(Action("", "log", None, self.t("grid_backup_off"), False), False)
        if sources_differ(sensor_kw, self.grid_evcc_kw):
            if self._diff_since is None:
                self._diff_since = now
            elif (now - self._diff_since).total_seconds() >= SOURCES_DIFFER_AFTER_S:
                self.sources_differ = True
                if not self._diff_noted:
                    self._diff_noted = True
                    self._log(Action("", "log", None, self.t("grid_differ", a=sensor_kw or 0.0, b=self.grid_evcc_kw or 0.0), False), False)
        else:
            self._diff_since, self.sources_differ, self._diff_noted = None, False, False
'''),
    ('''        states: dict[tuple[str, str], dict[str, Any] | None] = {}
        for dev_id, d in self.raw_devices.items():
            if d.get(D_KIND) != KIND_EVCC:
                continue
            key = (str(d.get(D_EVCC_URL) or ""), str(d.get(D_EVCC_PASSWORD) or ""))
            if key not in states:
                try:
                    states[key] = await self._evcc_client(*key).state()
                    self._evcc_down.discard(key)
                except Exception as err:  # noqa: BLE001 - evcc being down must not stop the guard
                    states[key] = None
                    if key not in self._evcc_down:  # say it once, not every cycle
                        _LOGGER.warning("evcc at %s is not reachable: %s", key[0], err)
                        self._evcc_down.add(key)
            self._evcc_lp[dev_id] = parse_loadpoint(states[key], int(d.get(D_EVCC_LOADPOINT) or 1)) if states[key] else None
''', '''        states: dict[tuple[str, str], dict[str, Any] | None] = {}

        async def read(key: tuple[str, str]) -> dict[str, Any] | None:
            if key not in states:
                try:
                    states[key] = await self._evcc_client(*key).state()
                    self._evcc_down.discard(key)
                except Exception as err:  # noqa: BLE001 - evcc being down must not stop the guard
                    states[key] = None
                    if key not in self._evcc_down:  # say it once, not every cycle
                        _LOGGER.warning("evcc at %s is not reachable: %s", key[0], err)
                        self._evcc_down.add(key)
            return states[key]

        for dev_id, d in self.raw_devices.items():
            if d.get(D_KIND) != KIND_EVCC:
                continue
            st = await read((str(d.get(D_EVCC_URL) or ""), str(d.get(D_EVCC_PASSWORD) or "")))
            self._evcc_lp[dev_id] = parse_loadpoint(st, int(d.get(D_EVCC_LOADPOINT) or 1)) if st else None
        site_url = str(self.cfg.get(CONF_EVCC_URL) or "")
        self.grid_evcc_kw = parse_grid_kw(await read((site_url, str(self.cfg.get(CONF_EVCC_PASSWORD) or "")))) if site_url else None
'''),
    ('''            "grid_power": self.cfg.get(CONF_GRID_POWER),
''', '''            "grid_power": self.cfg.get(CONF_GRID_POWER),
            "evcc_grid": bool(self.cfg.get(CONF_EVCC_URL)),
'''),
])

# ---- status attributes ----
edit("sensor.py", [(
    '''            "grid_stale": w.grid_stale,
''', '''            "grid_stale": w.grid_stale,
            "grid_source": w.grid_source,
            "grid_evcc_kw": w.grid_evcc_kw,
            "sources_differ": w.sources_differ,
''')])

# ---- dialog: the sensor is optional when evcc is entered ----
edit("config_flow.py", [
    ("from .const import D_EVCC_LOADPOINT, D_EVCC_ONE_PHASE, D_EVCC_PASSWORD, D_EVCC_URL\n",
     "from .const import CONF_EVCC_BACKUP, CONF_EVCC_PASSWORD, CONF_EVCC_URL, D_EVCC_LOADPOINT, D_EVCC_ONE_PHASE, D_EVCC_PASSWORD, D_EVCC_URL\n"),
    ("from .evcc import EvccAuthError, EvccClient, EvccError, parse_loadpoint\n",
     "from .evcc import EvccAuthError, EvccClient, EvccError, parse_grid_kw, parse_loadpoint\n"),
    ('''    s[vol.Required(CONF_GRID_POWER, default=d.get(CONF_GRID_POWER, vol.UNDEFINED))] = _ent("sensor")
    s[_opt(CONF_GRID_ENERGY, d)] = _ent("sensor")
''', '''    s[_opt(CONF_GRID_POWER, d)] = _ent("sensor")
    s[_opt(CONF_EVCC_URL, d)] = TextSelector()
    s[_opt(CONF_EVCC_PASSWORD, d)] = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
    if not first:
        s[vol.Required(CONF_EVCC_BACKUP, default=bool(d.get(CONF_EVCC_BACKUP, True)))] = BooleanSelector()
    s[_opt(CONF_GRID_ENERGY, d)] = _ent("sensor")
'''),
    ('''        if user_input is not None:
            errors = unit_errors(self.hass.states.get, user_input, (CONF_GRID_POWER,), (CONF_GRID_ENERGY,))
            if errors:
                return self.async_show_form(step_id="user", data_schema=_general_schema(user_input, True), errors=errors)
            data = {k: user_input[k] for k in (CONF_GRID_POWER, CONF_GRID_ENERGY) if user_input.get(k)}
''', '''        if user_input is not None:
            errors = unit_errors(self.hass.states.get, user_input, (CONF_GRID_POWER,), (CONF_GRID_ENERGY,)) or await _grid_source_errors(self.hass, user_input)
            if errors:
                return self.async_show_form(step_id="user", data_schema=_general_schema(user_input, True), errors=errors)
            data = {k: user_input[k] for k in (CONF_GRID_POWER, CONF_GRID_ENERGY, CONF_EVCC_URL, CONF_EVCC_PASSWORD) if user_input.get(k)}
'''),
    ('''            errors = unit_errors(self.hass.states.get, user_input, (CONF_GRID_POWER,), (CONF_GRID_ENERGY,))
            if errors:
                return self.async_show_form(step_id="init",''', '''            errors = unit_errors(self.hass.states.get, user_input, (CONF_GRID_POWER,), (CONF_GRID_ENERGY,)) or await _grid_source_errors(self.hass, user_input)
            if errors:
                return self.async_show_form(step_id="init",'''),
    ('''            if not user_input.get(CONF_GRID_ENERGY):
                keep[CONF_GRID_ENERGY] = ""  # cleared on purpose; overrides the value from set-up
''', '''            for cleared in (CONF_GRID_ENERGY, CONF_GRID_POWER, CONF_EVCC_URL, CONF_EVCC_PASSWORD):
                if not user_input.get(cleared):
                    keep[cleared] = ""  # cleared on purpose; overrides the value from set-up
'''),
    ('''def _device_schema(kind: str, d: dict[str, Any]) -> vol.Schema:''', '''async def _grid_source_errors(hass: Any, u: dict[str, Any]) -> dict[str, str]:
    """At least one source of the grid import is needed; an evcc address is tried right away (and must have a grid meter)."""
    url = str(u.get(CONF_EVCC_URL) or "").strip()
    if not u.get(CONF_GRID_POWER) and not url:
        return {CONF_GRID_POWER: "grid_source_missing"}
    if not url:
        return {}
    try:
        state = await EvccClient(async_get_clientsession(hass), url, u.get(CONF_EVCC_PASSWORD)).state()
    except EvccAuthError:
        return {CONF_EVCC_PASSWORD: "evcc_auth"}
    except EvccError:
        return {CONF_EVCC_URL: "evcc_unreachable"}
    if parse_grid_kw(state) is None:
        return {CONF_EVCC_URL: "evcc_no_grid"}
    return {}


def _device_schema(kind: str, d: dict[str, Any]) -> vol.Schema:'''),
])

# ---- texts of the dialog ----
TXT = {
    "strings.json": dict(
        data=dict(evcc_site_url="Address of evcc (optional)", evcc_site_password="Password of evcc", evcc_backup="evcc as a reserve for the grid import"),
        desc=dict(evcc_site_url="Optional: take the grid import from evcc (for example http://192.168.1.20:7070). Your own sensor above always wins.",
                  evcc_site_password="Only if evcc asks for a password.",
                  evcc_backup="While your sensor has no usable value (missing or too old) the guard uses evcc instead of giving everything back. It changes back by itself.",
                  grid_power="Sensor with the power drawn from the grid (W or kW). Negative values (export) count as 0. Optional if you enter evcc."),
        errors=dict(grid_source_missing="Enter a grid import sensor or the address of evcc.", evcc_unreachable="evcc cannot be reached at this address.",
                    evcc_auth="evcc asks for a password, or the password is wrong.", evcc_no_grid="evcc reports no grid meter (no grid power)."),
    ),
    "translations/de.json": dict(
        data=dict(evcc_site_url="Adresse von evcc (optional)", evcc_site_password="Passwort von evcc", evcc_backup="evcc als Reserve für den Netzbezug"),
        desc=dict(evcc_site_url="Optional: den Netzbezug aus evcc nehmen (zum Beispiel http://192.168.1.20:7070). Ihr eigener Sensor oben gilt immer zuerst.",
                  evcc_site_password="Nur wenn evcc ein Passwort verlangt.",
                  evcc_backup="Solange Ihr Sensor nichts Brauchbares liefert (fehlt oder zu alt), nimmt der Wächter evcc, statt alles zurückzugeben. Er wechselt von selbst zurück.",
                  grid_power="Sensor mit der Leistung, die aus dem Netz bezogen wird (W oder kW). Negative Werte (Einspeisung) zählen als 0. Optional, wenn Sie evcc eintragen."),
        errors=dict(grid_source_missing="Tragen Sie einen Sensor für den Netzbezug oder die Adresse von evcc ein.", evcc_unreachable="evcc ist unter dieser Adresse nicht erreichbar.",
                    evcc_auth="evcc verlangt ein Passwort, oder das Passwort ist falsch.", evcc_no_grid="evcc meldet keinen Netzzähler (keine Netzleistung)."),
    ),
}
TXT["translations/en.json"] = TXT["strings.json"]
for rel, L in TXT.items():
    p = PKG / rel
    raw = p.read_text(encoding="utf-8", newline="")
    crlf = "\r\n" in raw
    d = json.loads(raw)
    for step in (d["config"]["step"]["user"], d["options"]["step"]["init"]):
        step["data"].update(L["data"])
        step.setdefault("data_description", {}).update(L["desc"])
    d["config"].setdefault("error", {}).update(L["errors"])
    d["options"].setdefault("error", {}).update(L["errors"])
    out = json.dumps(d, indent=2, ensure_ascii=False) + "\n"
    if crlf:
        out = out.replace("\n", "\r\n")
    p.write_text(out, encoding="utf-8", newline="")
print("ok")
