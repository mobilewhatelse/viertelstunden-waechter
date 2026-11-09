"""One-off: 'observe only' per device and a warning when one wallbox seems to be entered twice (kept for the record).

User 2026-11-09: (1) warn when a wallbox device and an evcc loadpoint charge at the same time with nearly the same power (probably the
same wallbox entered twice), (2) a switch 'observe only' per device: the guard writes what it would do with that device, sends nothing to
it and does not count it as a lever (so it does not move on to other devices because of it).
"""
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


edit("const.py", [('D_HOLD = "hold_min"', 'D_OBSERVE = "observe_only"                # the guard only writes what it would do with this device\nD_HOLD = "hold_min"')])

# ---- engine: observe-only devices are no levers, but say what would happen ----
edit("engine.py", [
    ('''    pause_min: float = 0.0        # minimum pause after taking back before the next intervention (compressor protection)
''', '''    pause_min: float = 0.0        # minimum pause after taking back before the next intervention (compressor protection)
    observe_only: bool = False    # only say what would be done with it; never a lever, nothing is sent
'''),
    ('''            pause_min=float(d.get("pause_min", 0.0)),
        )''', '''            pause_min=float(d.get("pause_min", 0.0)),
            observe_only=bool(d.get("observe_only", False)),
        )'''),
    ('''    def _options(self, now: datetime, readings: dict[str, Reading], excess: float) -> list[_Option]:
        opts: list[_Option] = []
        for dev in self.devices.values():
            r = readings.get(dev.id)''', '''    def _options(self, now: datetime, readings: dict[str, Reading], excess: float, watched: bool = False) -> list[_Option]:
        """The levers that can lower the grid import now. `watched=True` returns the same for the devices set to observe only
        (they are never real levers)."""
        opts: list[_Option] = []
        for dev in self.devices.values():
            if dev.observe_only != watched:
                continue
            r = readings.get(dev.id)'''),
    ('''        checks = self._verify(now, readings)
        actions = self._forced_releases(now, readings)
        if not actions:
            if excess > 0.1:
                actions = self._reduce(now, excess, readings, forecast, limit_kw, rest_h)''', '''        checks = self._verify(now, readings)
        actions = self._forced_releases(now, readings)
        if excess > 0.1:
            actions = actions + self._watch_notes(now, readings, excess)
        if not [a for a in actions if a.kind != "log"]:
            if excess > 0.1:
                actions = actions + self._reduce(now, excess, readings, forecast, limit_kw, rest_h)'''),
    ('''    def _choose(self, opts: list[_Option], excess: float) -> list[_Option]:''', '''    def _watch_notes(self, now: datetime, readings: dict[str, Reading], excess: float) -> list[Action]:
        """For each device set to observe only: once per quarter hour, what the guard would take from it right now."""
        notes: list[Action] = []
        for o in self._options(now, readings, excess, watched=True):
            key = (o.device.id, self.quarter)
            if key in self._watch_noted:
                continue
            self._watch_noted.add(key)
            notes.append(Action(o.device.id, "log", None, self.t("watch", name=o.device.name, kw=o.reduction_kw, excess=excess), False))
        if len(self._watch_noted) > 200:
            self._watch_noted = {k for k in self._watch_noted if k[1] == self.quarter}
        return notes

    def _choose(self, opts: list[_Option], excess: float) -> list[_Option]:'''),
    ('''        self.t = Messages(lang)           # texts of the log lines in the language of Home Assistant
''', '''        self.t = Messages(lang)           # texts of the log lines in the language of Home Assistant
        self._watch_noted: set[tuple[str, Any]] = set()  # (device, quarter) already noted for observe-only devices
'''),
])

# ---- texts ----
msgs = (PKG / "messages.py").read_text(encoding="utf-8", newline="")
crlf = "\r\n" in msgs
msgs = msgs.replace("\r\n", "\n")
a_de = '        "grid_differ": "Netzbezug: Ihr Sensor zeigt'
assert msgs.count(a_de) == 1
msgs = msgs.replace(a_de,
    '        "watch": "Nur beobachten: {name} würde um {kw:.1f} kW gesenkt ({excess:.1f} kW zu viel), es wurde nichts gesendet",\n'
    '        "wb_twice": "Wallbox {a} und evcc-Ladepunkt {b} laden gleichzeitig mit fast gleicher Leistung ({kw:.1f} kW). Ist das dieselbe Wallbox? Bitte nur einmal eintragen.",\n'
    + a_de, 1)
a_en = '        "grid_differ": "Grid import: your sensor shows'
assert msgs.count(a_en) == 1
msgs = msgs.replace(a_en,
    '        "watch": "Observe only: {name} would be lowered by {kw:.1f} kW ({excess:.1f} kW too much), nothing was sent",\n'
    '        "wb_twice": "Wallbox {a} and evcc loadpoint {b} charge at the same time with nearly the same power ({kw:.1f} kW). Is it the same wallbox? Please enter it only once.",\n'
    + a_en, 1)
if crlf:
    msgs = msgs.replace("\n", "\r\n")
(PKG / "messages.py").write_text(msgs, encoding="utf-8", newline="")

# ---- coordinator: the warning for a wallbox entered twice ----
edit("coordinator.py", [
    ('''        self._on_backup = False
''', '''        self._on_backup = False
        self.wallbox_twice: str | None = None   # "wallbox name / evcc name" while both seem to be the same wallbox
        self._twice_since: datetime | None = None
        self._twice_noted = False
'''),
    ('''            self._wb_accumulate(now, readings)
''', '''            self._wb_accumulate(now, readings)
            self._watch_wallbox_twice(now, readings)
'''),
    ('''    def _watch_sources(self, sensor_kw: float | None, source: str | None, now: datetime) -> None:''', '''    def _watch_wallbox_twice(self, now: datetime, readings: dict[str, Reading]) -> None:
        """A wallbox device and an evcc loadpoint that charge at the same time with nearly the same power for two minutes are
        probably the same wallbox entered twice (two controllers on one wallbox). Say it once per episode; nothing is changed."""
        pair: tuple[str, str, float] | None = None
        for wid, wd in self.raw_devices.items():
            if wd.get(D_KIND) != KIND_WALLBOX:
                continue
            pw = (readings.get(wid) or Reading()).power_w or 0.0
            for eid, ed in self.raw_devices.items():
                if ed.get(D_KIND) != KIND_EVCC:
                    continue
                pe = (readings.get(eid) or Reading()).power_w or 0.0
                if pw > 1000 and pe > 1000 and abs(pw - pe) <= 0.15 * max(pw, pe):
                    pair = (str(wd.get(D_NAME)), str(ed.get(D_NAME)), max(pw, pe) / 1000.0)
        if pair is None:
            self._twice_since, self._twice_noted, self.wallbox_twice = None, False, None
            return
        if self._twice_since is None:
            self._twice_since = now
        elif (now - self._twice_since).total_seconds() >= SOURCES_DIFFER_AFTER_S:
            self.wallbox_twice = f"{pair[0]} / {pair[1]}"
            if not self._twice_noted:
                self._twice_noted = True
                self._log(Action("", "log", None, self.t("wb_twice", a=pair[0], b=pair[1], kw=pair[2]), False), False)

    def _watch_sources(self, sensor_kw: float | None, source: str | None, now: datetime) -> None:'''),
])
edit("sensor.py", [(
    '''            "sources_differ": w.sources_differ,
''', '''            "sources_differ": w.sources_differ,
            "wallbox_twice": w.wallbox_twice,
''')])

# ---- dialog: the switch in every device (not the car plan) ----
edit("config_flow.py", [
    ("    D_COMFORT, D_COMFORT_MIN, D_HOLD,", "    D_COMFORT, D_COMFORT_MIN, D_HOLD, D_OBSERVE,"),
])
s = (PKG / "config_flow.py").read_text(encoding="utf-8", newline="")
crlf = "\r\n" in s
s = s.replace("\r\n", "\n")
i = s.index("def _device_schema(")
j = s.index("    return vol.Schema(s)\n", i)
s = s[:j] + ("    if kind != KIND_VEHICLE:\n"
             "        s[vol.Required(D_OBSERVE, default=bool(d.get(D_OBSERVE, False)))] = BooleanSelector()\n") + s[j:]
t_i = s.index("def device_title(")
t_j = s.index('    return f"{prio} · {d.get(D_NAME, \'?\')} · {what}"', t_i)
s = s[:t_j] + '    if d.get(D_OBSERVE):\n        what += " · nur beobachten"\n' + s[t_j:]
if crlf:
    s = s.replace("\n", "\r\n")
(PKG / "config_flow.py").write_text(s, encoding="utf-8", newline="")

TXT = {
    "strings.json": ("Observe only", "The guard only writes to the log what it would do with this device. Nothing is sent to it and it does not count as a lever. Good for trying a new device first."),
    "translations/en.json": ("Observe only", "The guard only writes to the log what it would do with this device. Nothing is sent to it and it does not count as a lever. Good for trying a new device first."),
    "translations/de.json": ("Nur beobachten", "Der Wächter schreibt nur ins Protokoll, was er mit diesem Gerät tun würde. Es wird nichts gesendet, und das Gerät zählt nicht als Hebel. Gut, um ein neues Gerät zuerst auszuprobieren."),
}
for rel, (label, desc) in TXT.items():
    p = PKG / rel
    raw = p.read_text(encoding="utf-8", newline="")
    crlf = "\r\n" in raw
    d = json.loads(raw)
    for kind, sub in d["config_subentries"].items():
        if kind == "vehicle":
            continue
        for step in sub.get("step", {}).values():
            step.setdefault("data", {})["observe_only"] = label
            step.setdefault("data_description", {})["observe_only"] = desc
    out = json.dumps(d, indent=2, ensure_ascii=False) + "\n"
    if crlf:
        out = out.replace("\n", "\r\n")
    p.write_text(out, encoding="utf-8", newline="")
print("ok")
