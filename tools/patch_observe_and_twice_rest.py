"""One-off: second half of patch_observe_and_twice.py (the first half had run already; kept for the record)."""

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


# ---- coordinator: the warning for a wallbox entered twice ----
edit("coordinator.py", [
    ('''        self._diff_noted = False
        self._on_backup = False
''', '''        self._diff_noted = False
        self._on_backup = False
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
