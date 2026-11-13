"""Device check, the measuring part: what the guard sees of every connected device, collected locally.

The judgement (is this a loss of power, a missing phase, a battery that holds less, a pump that needs more?) is made by the
check service; the guard sends the measured values only while *Share anonymous data* is switched on and shows the answer.
Sent are measured values without date, time of day or any id (days only as "days ago"); the service keeps nothing of a check
except anonymous daily values for the comparison with the same devices of others.

Measured here:
- wallbox / evcc loadpoint: per charge the share of what the current setting allows (amps x phases x voltage), measured over
  10 minutes with the same setting (a throttling by the guard or by evcc lowers the setting too, so it is never a fault),
  and the power at the highest setting
- home battery: per swing of the state of charge the energy per percentage point (usable capacity), with its direction
- switchable devices: the mean power of every run of at least 10 minutes, the share of the on-time in which it drew, and how long
  it has been switched on without drawing
- every device: energy, highest power and running time per day, with the mean outdoor temperature
- for the comparison with the same devices of others, values that do not depend on the size of the house: a home battery's
  capacity as a share of its own base value and its age in half years; a heat pump's day against its own curve at the same
  outdoor temperature and the shape of that curve (cold against mild); a water heater's day against its own mean
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

SCHEMA = 1
WINDOW_S = 600                 # a measurement needs the same setting for 10 minutes
CHARGING_W = 1000.0            # the wallbox counts as charging above this
SESSION_GAP_S = 900            # a new charge after 15 minutes without charging
CAR_FULL_SOC = 85.0            # above this the car limits by itself: not measured
COLD_C = 0.0                   # below this outdoor temperature the car may limit by itself: not measured
SWING_MIN = 40.0               # a swing of the battery is kept from 40 percentage points on
BASE_SWINGS = 10               # the first 10 swings are kept for good: they are the base value
SWING_IDLE_S = 7200            # a swing ends after 2 hours without change ...
SWING_TURN = 2.0               # ... or when the state of charge goes 2 points the other way
ON_W = 50.0                    # a device counts as running above this
RUN_MIN_S = 600                # a run is kept from 10 minutes on
QUIET_W_SHARE = 0.10           # "on without drawing": below 10 % of its usual run power

KEEP_SESSIONS = 60
KEEP_RUNS = 80
KEEP_SWINGS = 40
KEEP_DAYS = 400
SEND_DAYS = 120                # days per device in a check request
CURVE_DAYS = 21                # a heat pump needs this many days with temperature for its own curve
CURVE_SPAN_K = 8.0             # ... over at least this many kelvin for the shape cold/mild
MEAN_DAYS = 14                 # a water heater needs this many days for its own mean
BASE_FOR_PCT = 3               # swings of the base value before a battery's capacity is given in percent of it
MAX_STEP_S = 120               # a gap longer than this is not integrated

ART_HEAT_PUMP = "heat_pump"
ART_WATER_HEATER = "water_heater"
ART_PUMP = "pump"
ART_OTHER = "other"
ARTS = (ART_HEAT_PUMP, ART_WATER_HEATER, ART_PUMP, ART_OTHER)

SERVICE_URL = "https://www.aiwhatelse.eu/geraete/v1/pruefen.php"
CHECK_EVERY_H = 24             # one check a day
RETRY_H = 6                    # after a failed check (server not reachable)

TEXTS = {
    "de": {
        "wb_phase": "{name} lädt nur mit {anteil_pct} % der eingestellten Leistung (etwa {band}), bei {ladungen} Ladungen. Fehlt eine Phase? "
                    "Sicherung, Kabel und Stecker prüfen.",
        "wb_low": "{name} lädt nur mit {anteil_pct} % der eingestellten Leistung, bei {ladungen} Ladungen. Kabel, Stecker und Anschluss prüfen.",
        "wb_trend": "{name} lädt bei voller Vorgabe nur noch mit {jetzt_kw} kW, früher {frueher_kw} kW ({pct} %).",
        "bat_low": "{name} speichert nur noch {jetzt_kwh} kWh, am Anfang waren es {grund_kwh} kWh ({pct} %).",
        "sw_more": "{name} braucht {pct} % mehr als sonst: {jetzt_w} W statt {gelernt_w} W.",
        "sw_nothing": "{name} ist seit {minuten} Minuten eingeschaltet, zieht aber keinen Strom (sonst {gelernt_w} W).",
        "hp_more": "{name} braucht bei gleicher Außentemperatur {pct} % mehr Strom als sonst (letzte {tage} Tage).",
        "wh_more": "{name} braucht {pct} % mehr Strom am Tag als im Mittel ({mittel_kwh} kWh).",
    },
    "en": {
        "wb_phase": "{name} charges with only {anteil_pct} % of the set power (about {band}) over {ladungen} charges. Is a phase missing? "
                    "Check the fuse, cable and plug.",
        "wb_low": "{name} charges with only {anteil_pct} % of the set power over {ladungen} charges. Check the cable, plug and connection.",
        "wb_trend": "{name} reaches only {jetzt_kw} kW at the full setting, earlier {frueher_kw} kW ({pct} %).",
        "bat_low": "{name} stores only {jetzt_kwh} kWh, at the start it was {grund_kwh} kWh ({pct} %).",
        "sw_more": "{name} needs {pct} % more than usual: {jetzt_w} W instead of {gelernt_w} W.",
        "sw_nothing": "{name} has been switched on for {minuten} minutes but draws no power (usually {gelernt_w} W).",
        "hp_more": "{name} needs {pct} % more power than usual at the same outdoor temperature (last {tage} days).",
        "wh_more": "{name} needs {pct} % more power a day than on average ({mittel_kwh} kWh).",
    },
}


class _Blank(dict):
    def __missing__(self, key: str) -> str:
        return "?"


def text(lang: str, key: str, name: str, values: dict[str, Any]) -> str:
    """The sentence for a finding, in the language of Home Assistant."""
    t = TEXTS["de" if str(lang or "").startswith("de") else "en"]
    return t.get(key, "{name}: " + key).format_map(_Blank({**{k: v for k, v in (values or {}).items()}, "name": name}))


WALLBOX_KINDS = ("wallbox", "evcc")
BATTERY_KINDS = ("battery",)
SWITCH_KINDS = ("switch", "setting", "throttle", "script")
LEVELS = ("ok", "hint", "warn", "learning", "none")


@dataclass
class Sample:
    """One device in one cycle, as far as it is known."""

    kind: str
    art: str | None = None
    power_w: float | None = None       # consumption of the device (W)
    current_a: float | None = None     # wallbox: current setting (A)
    phases: int | None = None          # wallbox: phases in use
    max_current: float | None = None   # wallbox: highest setting (A), for "full power"
    is_on: bool | None = None          # switch: on/off of its own switch
    soc: float | None = None           # battery: state of charge; wallbox: state of charge of the car
    battery_w: float | None = None     # battery: power into or out of the battery (any sign)
    intervened: bool = False           # the guard has changed this device right now


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def _fit(days: list) -> tuple[float, float] | None:
    """Straight line kWh per day over the outdoor temperature (rows [date, kwh, max_kw, hours, temp]), from days with energy and
    temperature; None with fewer than CURVE_DAYS of them or no spread of the temperature."""
    pts = [(float(r[4]), float(r[1])) for r in days if r[4] is not None and r[1] and r[1] > 0]
    if len(pts) < CURVE_DAYS:
        return None
    mt = sum(p[0] for p in pts) / len(pts)
    mk = sum(p[1] for p in pts) / len(pts)
    var = sum((p[0] - mt) ** 2 for p in pts)
    if var <= 0:
        return None
    slope = sum((p[0] - mt) * (p[1] - mk) for p in pts) / var
    return mk - slope * mt, slope


def _span(days: list) -> float:
    temps = [float(r[4]) for r in days if r[4] is not None and r[1] and r[1] > 0]
    return max(temps) - min(temps) if temps else 0.0


def _days_between(a: str, b: str) -> int:
    try:
        return (datetime.strptime(b, "%Y-%m-%d") - datetime.strptime(a, "%Y-%m-%d")).days
    except ValueError:
        return 0


class DeviceCheck:
    """Measured values of all devices; `step` once per cycle, `request` builds what is sent, `apply` takes the answer."""

    def __init__(self, voltage: float = 230.0) -> None:
        self.voltage = voltage
        self.dev: dict[str, dict[str, Any]] = {}
        self.result: dict[str, dict[str, Any]] = {}   # the last answer of the service, per device id
        self.checked_at: str | None = None
        self.new_days: list[dict[str, Any]] = []     # finished days not sent yet (anonymous, without date)
        self.changed = False                          # something new was measured since the last check
        self._last: datetime | None = None

    # ---------- persistence ----------

    def to_dict(self) -> dict[str, Any]:
        return {"dev": self.dev, "result": self.result, "checked_at": self.checked_at, "new_days": self.new_days[-KEEP_DAYS:],
                "changed": self.changed}

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None, voltage: float = 230.0) -> DeviceCheck:
        c = cls(voltage)
        d = d or {}
        c.dev = d.get("dev") or {}
        c.result = d.get("result") or {}
        c.checked_at = d.get("checked_at")
        c.new_days = list(d.get("new_days") or [])
        c.changed = bool(d.get("changed"))
        return c

    def forget(self, keep: set[str]) -> None:
        """Drop devices that are no longer entered."""
        self.dev = {k: v for k, v in self.dev.items() if k in keep}
        self.result = {k: v for k, v in self.result.items() if k in keep}

    # ---------- measuring ----------

    def step(self, now: datetime, samples: dict[str, Sample], temp_c: float | None) -> None:
        dt = 0.0 if self._last is None else max(0.0, (now - self._last).total_seconds())
        self._last = now
        if dt > MAX_STEP_S:
            dt = 0.0
        for dev_id, s in samples.items():
            st = self.dev.setdefault(dev_id, {})
            st["kind"], st["art"] = s.kind, s.art
            self._day(dev_id, st, now, s, temp_c, dt)
            if s.kind in WALLBOX_KINDS:
                self._wallbox(st, now, s, temp_c)
            elif s.kind in BATTERY_KINDS:
                self._battery(st, now, s, dt)
            elif s.kind in SWITCH_KINDS:
                self._switch(st, now, s, dt)

    def _day(self, dev_id: str, st: dict[str, Any], now: datetime, s: Sample, temp_c: float | None, dt: float) -> None:
        today = now.strftime("%Y-%m-%d")
        cur = st.get("today")
        if cur and cur.get("d") != today:
            self._close_day(st, cur, dev_id)
            cur = None
        if cur is None:
            cur = st["today"] = {"d": today, "kwh": 0.0, "max_kw": 0.0, "on_s": 0.0, "t_sum": 0.0, "t_s": 0.0}
        p = s.power_w if s.kind not in BATTERY_KINDS else (abs(s.battery_w) if s.battery_w is not None else None)
        if p is not None:
            p = max(0.0, p)
            cur["max_kw"] = max(cur["max_kw"], p / 1000.0)
            if dt > 0:
                cur["kwh"] += p * dt / 3_600_000.0
                if p >= ON_W:
                    cur["on_s"] += dt
        if temp_c is not None and dt > 0:
            cur["t_sum"] += temp_c * dt
            cur["t_s"] += dt

    def _close_day(self, st: dict[str, Any], cur: dict[str, Any], dev_id: str = "") -> None:
        temp = round(cur["t_sum"] / cur["t_s"], 1) if cur.get("t_s") else None
        row = [cur["d"], round(cur["kwh"], 3), round(cur["max_kw"], 3), round(cur["on_s"] / 3600.0, 2), temp]
        days = st.setdefault("days", [])
        days.append(row)
        del days[:-KEEP_DAYS]
        self.changed = True
        if row[1] <= 0 and row[2] <= 0:
            return
        shared: dict[str, Any] = {"dev": dev_id, "kwh": row[1], "max_kw": row[2], "laufzeit_h": row[3], "temp_c": temp}
        if st.get("kind") in WALLBOX_KINDS and st.get("day_share") is not None:
            shared["anteil_vorgabe"] = round(st["day_share"], 3)
        if st.get("kind") in BATTERY_KINDS and st.get("day_cap") is not None:
            shared["kapazitaet_kwh"] = round(st["day_cap"], 2)
            base = (st.get("bat") or {}).get("base") or []
            if len(base) >= BASE_FOR_PCT:
                ref = sum(x[0] for x in base) / len(base)
                if ref > 0:
                    shared["kapazitaet_pct"] = round(st["day_cap"] / ref * 100.0, 1)
        rel = self._relative(st, row)
        if rel is not None:
            shared["rel_kurve"] = rel
        st["day_share"] = st["day_cap"] = None
        self.new_days.append(shared)
        del self.new_days[:-KEEP_DAYS]

    @staticmethod
    def _relative(st: dict[str, Any], row: list) -> float | None:
        """The finished day against the device's own past (without this day): a heat pump against its curve at the same outdoor
        temperature, a water heater against its mean. Size of the house and of the tank drop out."""
        before = st.get("days", [])[:-1]
        if not row[1] or row[1] <= 0:
            return None
        if st.get("art") == ART_HEAT_PUMP and row[4] is not None:
            fit = _fit(before[-SEND_DAYS:])
            if fit is None:
                return None
            expected = fit[0] + fit[1] * float(row[4])
            return round(row[1] / expected, 3) if expected > 0.1 else None
        if st.get("art") == ART_WATER_HEATER:
            ks = [float(r[1]) for r in before[-30:] if r[1] and r[1] > 0]
            if len(ks) < MEAN_DAYS:
                return None
            mean = sum(ks) / len(ks)
            return round(row[1] / mean, 3) if mean > 0.05 else None
        return None

    def _wallbox(self, st: dict[str, Any], now: datetime, s: Sample, temp_c: float | None) -> None:
        w = st.setdefault("wb", {"sessions": [], "win": None, "sess": None, "last_charge": None})
        ts = now.timestamp()
        charging = (s.power_w or 0.0) >= CHARGING_W
        if charging:
            if w["sess"] is None or (w["last_charge"] is not None and ts - w["last_charge"] > SESSION_GAP_S):
                self._end_session(w)
                w["sess"] = {"d": now.strftime("%Y-%m-%d"), "best": None, "full_kw": None}
            w["last_charge"] = ts
        elif w["sess"] is not None and w["last_charge"] is not None and ts - w["last_charge"] > SESSION_GAP_S:
            self._end_session(w)
        ok = (charging and not s.intervened and s.current_a and s.current_a > 0
              and (s.soc is None or s.soc < CAR_FULL_SOC) and (temp_c is None or temp_c >= COLD_C))
        if not ok:
            w["win"] = None
            return
        phases = s.phases if s.phases and s.phases > 0 else 3
        key = [round(float(s.current_a), 1), phases]
        win = w["win"]
        if win is None or win["key"] != key:
            w["win"] = {"key": key, "t0": ts, "sum": 0.0, "n": 0}
            return
        win["sum"] += float(s.power_w)
        win["n"] += 1
        if ts - win["t0"] < WINDOW_S:
            return
        mean_w = win["sum"] / win["n"]
        expected = key[0] * phases * self.voltage
        w["win"] = {"key": key, "t0": ts, "sum": 0.0, "n": 0}
        if expected <= 0 or w["sess"] is None:
            return
        share = mean_w / expected
        sess = w["sess"]
        sess["best"] = share if sess["best"] is None else max(sess["best"], share)
        if s.max_current and key[0] >= s.max_current - 0.5:
            sess["full_kw"] = max(sess.get("full_kw") or 0.0, mean_w / 1000.0)
        st["day_share"] = sess["best"] if st.get("day_share") is None else max(st["day_share"], sess["best"])

    def _end_session(self, w: dict[str, Any]) -> None:
        sess, w["sess"] = w["sess"], None
        if not sess or sess.get("best") is None:
            return
        w["sessions"].append([sess["d"], round(sess["best"], 3), round(sess["full_kw"], 3) if sess.get("full_kw") else None])
        del w["sessions"][:-KEEP_SESSIONS]
        self.changed = True

    def _battery(self, st: dict[str, Any], now: datetime, s: Sample, dt: float) -> None:
        b = st.setdefault("bat", {"base": [], "swings": [], "cur": None})
        if s.soc is None or s.battery_w is None:
            return
        ts = now.timestamp()
        cur = b["cur"]
        if cur is None:
            b["cur"] = {"soc0": s.soc, "peak": s.soc, "dir": 0, "kwh": 0.0, "t": ts}
            return
        cur["kwh"] += abs(s.battery_w) * dt / 3_600_000.0
        if cur["dir"] == 0 and abs(s.soc - cur["soc0"]) >= SWING_TURN:
            cur["dir"] = 1 if s.soc > cur["soc0"] else -1
        turned = cur["dir"] != 0 and (s.soc - cur["peak"]) * cur["dir"] <= -SWING_TURN
        if (cur["dir"] >= 0 and s.soc > cur["peak"]) or (cur["dir"] <= 0 and s.soc < cur["peak"]):
            cur["peak"], cur["t"] = s.soc, ts
        if turned or ts - cur["t"] > SWING_IDLE_S:
            span = abs(cur["peak"] - cur["soc0"])
            if span >= SWING_MIN and cur["kwh"] > 0:
                cap = cur["kwh"] / span * 100.0
                sw = [round(cap, 3), cur["dir"], round(span)]
                base = b.setdefault("base", [])
                if len(base) < BASE_SWINGS:
                    base.append(sw)
                    b.setdefault("seit", now.strftime("%Y-%m-%d"))   # first swing: the age counts from here
                else:
                    b["swings"].append(sw)
                    del b["swings"][:-KEEP_SWINGS]
                st["day_cap"] = cap
                self.changed = True
            b["cur"] = {"soc0": s.soc, "peak": s.soc, "dir": 0, "kwh": 0.0, "t": ts}

    def _switch(self, st: dict[str, Any], now: datetime, s: Sample, dt: float) -> None:
        if s.power_w is None:
            return
        w = st.setdefault("sw", {"runs": [], "run": None, "on_s": 0.0, "draw_s": 0.0, "quiet_since": None, "drew_before": None})
        ts = now.timestamp()
        running = s.power_w >= ON_W
        if s.is_on and not s.intervened and dt > 0:
            w["on_s"] += dt
            if running:
                w["draw_s"] += dt
        if running and not s.intervened:
            r = w["run"]
            if r is None:
                w["run"] = {"t0": ts, "sum": 0.0, "n": 0}
            else:
                r["sum"] += s.power_w
                r["n"] += 1
        elif w["run"] is not None:
            r, w["run"] = w["run"], None
            if ts - r["t0"] >= RUN_MIN_S and r["n"]:
                w["runs"].append(round(r["sum"] / r["n"], 1))
                del w["runs"][:-KEEP_RUNS]
                self.changed = True
        usual = sorted(w["runs"])[len(w["runs"]) // 2] if w["runs"] else None
        if s.is_on and not s.intervened and usual and s.power_w < QUIET_W_SHARE * usual:
            if w["quiet_since"] is None:
                # the share of the on-time with power, from before this quiet spell (the spell itself lowers it)
                w["quiet_since"] = ts
                w["drew_before"] = round(w["draw_s"] / w["on_s"], 3) if w["on_s"] > 0 else None
        else:
            if w["quiet_since"] is not None:
                self.changed = True
            w["quiet_since"] = None

    # ---------- what is sent and what comes back ----------

    def request(self, now: datetime, info: dict[str, dict[str, Any]], version: str) -> dict[str, Any]:
        """The check request: per device its kind, type, maker and model (from `info`) and the measured values. Days are given
        as 'days ago', the history of days only as a list in order; no date, time of day or id of the installation."""
        today = now.strftime("%Y-%m-%d")
        out: list[dict[str, Any]] = []
        self._ids = list(self.dev)
        for nr, dev_id in enumerate(self._ids):
            st = self.dev[dev_id]
            i = info.get(dev_id, {})
            g: dict[str, Any] = {"nr": nr, "geraet": st.get("kind"), "art": st.get("art"),
                                 "hersteller": i.get("hersteller"), "modell": i.get("modell")}
            if st.get("kind") in WALLBOX_KINDS:
                g["ladungen"] = [[_days_between(r[0], today), r[1], r[2]] for r in (st.get("wb") or {}).get("sessions", [])]
            elif st.get("kind") in BATTERY_KINDS:
                g["grund"] = [list(x) for x in (st.get("bat") or {}).get("base", [])]
                g["huebe"] = [list(x) for x in (st.get("bat") or {}).get("swings", [])]
                if i.get("nennkapazitaet_kwh"):
                    g["nennkapazitaet_kwh"] = i["nennkapazitaet_kwh"]
                seit = (st.get("bat") or {}).get("seit")
                if seit:
                    g["alter_halbjahre"] = max(0, _days_between(seit, today)) // 182
            elif st.get("kind") in SWITCH_KINDS:
                w = st.get("sw") or {}
                g["laeufe"] = list(w.get("runs", []))
                g["zog_wenn_an"] = w.get("drew_before") if w.get("quiet_since") else (
                    round(w["draw_s"] / w["on_s"], 3) if w.get("on_s") else None)
                g["an_ohne_strom_min"] = round((now.timestamp() - w["quiet_since"]) / 60) if w.get("quiet_since") else 0
            if st.get("art") == ART_HEAT_PUMP:
                recent = st.get("days", [])[-SEND_DAYS:]
                fit = _fit(recent)
                if fit is not None and _span(recent) >= CURVE_SPAN_K and fit[0] + fit[1] * 10.0 > 0.1:
                    g["form_kalt_mild"] = round((fit[0]) / (fit[0] + fit[1] * 10.0), 3)   # kWh at 0 deg C against 10 deg C
            g["tage"] = [[r[1], r[4]] for r in st.get("days", [])[-SEND_DAYS:]]
            out.append(g)
        nr = {dev_id: i for i, dev_id in enumerate(self._ids)}
        days = [{"nr": nr[t["dev"]], **{k: v for k, v in t.items() if k != "dev"}} for t in self.new_days if t.get("dev") in nr]
        return {"schema": SCHEMA, "integration": "viertelstunden_waechter", "version": version, "geraete": out, "neue_tage": days}

    def apply(self, now: datetime, answer: dict[str, Any]) -> None:
        """Take the answer of the service: per device status, findings and what it learned so far."""
        ids = getattr(self, "_ids", list(self.dev))
        res: dict[str, dict[str, Any]] = {}
        for g in answer.get("geraete") or []:
            try:
                dev_id = ids[int(g["nr"])]
            except (KeyError, IndexError, TypeError, ValueError):
                continue
            status = g.get("status") if g.get("status") in LEVELS else "none"
            befunde = [b for b in (g.get("befunde") or []) if isinstance(b, dict) and b.get("level") in ("hint", "warn")
                       and isinstance(b.get("key"), str)]
            res[dev_id] = {"status": status, "befunde": befunde, "werte": g.get("werte") if isinstance(g.get("werte"), dict) else {},
                           "lernt": g.get("lernt") if isinstance(g.get("lernt"), list) else None}
        self.result = res
        self.checked_at = now.isoformat(timespec="minutes")
        self.new_days = []
        self.changed = False

    def clear(self) -> None:
        """Sharing switched off: no check any more (the measured values stay local)."""
        self.result = {}
        self.checked_at = None

    def findings(self) -> dict[str, dict[str, Any]]:
        """Active findings: 'device_id:key' -> {device_id, key, level, werte}."""
        out = {}
        for dev_id, r in self.result.items():
            for b in r.get("befunde", []):
                out[f"{dev_id}:{b['key']}"] = {"device_id": dev_id, "key": b["key"], "level": b["level"], "werte": b.get("werte") or {}}
        return out

    def state(self) -> str:
        if not self.result:
            return "none"
        st = [r["status"] for r in self.result.values()]
        for level in ("warn", "hint"):
            if level in st:
                return level
        if all(s in ("learning", "none") for s in st):
            return "learning"
        return "ok"

    def measured(self) -> dict[str, dict[str, Any]]:
        """What is measured so far per device (shown locally, also without the service)."""
        out = {}
        for dev_id, st in self.dev.items():
            m: dict[str, Any] = {"kind": st.get("kind"), "days": len(st.get("days", []))}
            if st.get("kind") in WALLBOX_KINDS:
                ss = (st.get("wb") or {}).get("sessions", [])
                m["charges"] = len(ss)
                if ss:
                    m["last_share_pct"] = round(ss[-1][1] * 100)
                full = [r[2] for r in ss if r[2]]
                if full:
                    m["full_kw"] = round(_mean(full[-10:]) or 0.0, 2)
            elif st.get("kind") in BATTERY_KINDS:
                b = st.get("bat") or {}
                sw = b.get("base", []) + b.get("swings", [])
                m["swings"] = len(sw)
                if sw:
                    m["last_kwh"] = round(sw[-1][0], 2)
            elif st.get("kind") in SWITCH_KINDS:
                runs = (st.get("sw") or {}).get("runs", [])
                m["runs"] = len(runs)
                if runs:
                    m["usual_w"] = round(sorted(runs)[len(runs) // 2])
            out[dev_id] = m
        return out
