"""Local log (0.15.1): what the forecast said and what came, and how devices start. Stays in Home Assistant, nothing is sent.

Forecast log, one row per quarter hour: the projection of the running quarter hour (`forecast_kw`, "if the power stays as it is
now") after 1, 3, 5 and 10 minutes, "typical" and "high" of the load forecast for that quarter hour (as the sensor shows them,
with the car plan or a running charge) and the same for the house alone, the end value (energy of the quarter hour as kW) and
flags. It is the ground for looking back (how good was the projection, which safety margin would have been enough); it cannot
be collected later.

Start log, one row per run of a switchable device, a heat pump (setting) or a wallbox: the highest power in the first minutes,
the steady power, the seconds until the power stays steady and, at a wallbox, the seconds until it reaches what the current
setting allows. Ground for a later "block before it starts" (issue #5); nothing is switched by it.

Kept compactly: per day one text per log (numbers separated by commas, rows by semicolons), 400 days. Neither log goes into the
bug report or the diagnostics; those only say how many days there are. Pure functions here (tested without Home Assistant).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median
from typing import Any

SCHEMA = 1
KEEP_DAYS = 400               # like the device check
RECENT_DAYS = 3               # the small store holds the last days and is written often; the big one about once a day
MARKS_S = (60, 180, 300, 600)  # projection after 1, 3, 5 and 10 minutes ...
MARK_WINDOW_S = 60            # ... taken only within the minute after the mark (after a gap the mark stays empty)
OPEN_MAX_S = 1800             # a quarter hour without an end value (Home Assistant was away at its end) is closed after this

# fields of a quarter-hour row (after the slot of the day, 0 = 00:00 ... 95 = 23:45; kW as hundredths, flags as bits)
Q_FIELDS = ("m1", "m3", "m5", "m10", "typ", "hoch", "haus_typ", "haus_hoch", "ende", "flags")
Q_TYP, Q_HOCH, Q_HAUS_TYP, Q_HAUS_HOCH, Q_ENDE, Q_FLAGS = 4, 5, 6, 7, 8, 9
F_EINGRIFF = 1                # the guard reduced a device in this quarter hour (really, not in observe mode)
F_GESCHAETZT = 2              # the quarter hour began with a guess or a counter gap: the end value is no clean measurement

# fields of a start row (after the device number): start (minute of the day), peak W, steady W, s until steady, s until the
# setting is reached (wallbox), seconds between two new values of the power sensor, flags
A_FIELDS = ("start_min", "spitze_w", "dauer_w", "stabil_s", "vorgabe_s", "abstand_s", "flags")
A_EINGRIFF = 1                # the guard changed the device during the start
A_KURZ = 2                    # the run ended before the window was over (values from a shorter time)
A_GROB = 4                    # the power sensor reports seldom (30 s or more): the start is only coarsely seen

RUN_KINDS = ("switch", "setting", "wallbox", "evcc")
START_W = {"wallbox": 1000.0, "evcc": 1000.0, "setting": 150.0, "switch": 50.0}   # a run begins above this
OFF_S = 60                    # ... after at least this long below it (a short dip is no new start)
CYCLE_S = 20                  # the guard's cycle: the time below counts from the first to one cycle after the last low value
WINDOW_S = 600                # a start is looked at for 10 minutes
PEAK_S = 180                  # "peak in the first minutes": the first 3 minutes
STEADY_FROM_S = 300           # steady power: median from minute 5 to 10
BAND_SHARE = 0.10             # steady = within 10 % of the steady power ...
BAND_MIN_W = 50.0             # ... but at least 50 W
TARGET_SHARE = 0.90           # wallbox: the setting counts as reached at 90 % of amps x phases x voltage
COARSE_GAP_S = 30.0


def _c(kw: Any) -> int | None:
    """kW as hundredths (0.01 kW), None stays None."""
    if kw is None:
        return None
    try:
        return max(0, min(999_999, int(round(float(kw) * 100.0))))
    except (TypeError, ValueError):
        return None


def _enc(values: list[Any]) -> str:
    """Numbers separated by commas, an empty field for a missing value, empty fields at the end left out."""
    out = ["" if v is None else str(int(v)) for v in values]
    while out and out[-1] == "":
        out.pop()
    return ",".join(out)


def _dec(text: str, n: int) -> list[int | None]:
    parts = text.split(",") if text else []
    out: list[int | None] = []
    for p in parts[:n]:
        try:
            out.append(int(p) if p != "" else None)
        except ValueError:
            out.append(None)
    return out + [None] * (n - len(out))


def _slot(t: datetime) -> int:
    return t.hour * 4 + t.minute // 15


def _quarter(t: datetime) -> datetime:
    return t.replace(minute=(t.minute // 15) * 15, second=0, microsecond=0)


class Protokoll:
    """Both logs. `days`: "YYYY-MM-DD" -> {"q": rows of quarter hours, "a": rows of starts}, each one text."""

    def __init__(self) -> None:
        self.days: dict[str, dict[str, str]] = {}
        self.devs: list[str] = []                       # device ids, the number in a start row is the position here
        self.open: dict[str, list[int | None]] = {}     # quarter hours still running or waiting for their end value
        self._closed: list[str] = []                    # the last closed quarter hours (never written twice)
        self._changed: set[str] = set()                 # days changed since the big store was last written

    # ---------- persistence ----------

    @classmethod
    def from_store(cls, archive: Any, recent: Any = None) -> Protokoll:
        """Both stores; the small one (written often) wins for its days. Anything unreadable is left out, never an error."""
        p = cls()
        for src in (archive, recent):
            if not isinstance(src, dict):
                continue
            devs = src.get("devs")
            if isinstance(devs, list) and len(devs) >= len(p.devs):
                p.devs = [str(x) for x in devs]
            for day, v in (src.get("days") or {}).items() if isinstance(src.get("days"), dict) else ():
                if isinstance(day, str) and len(day) == 10 and isinstance(v, dict):
                    kept = {k: v[k] for k in ("q", "a") if isinstance(v.get(k), str) and v[k]}
                    if kept:
                        p.days[day] = kept
        if isinstance(recent, dict) and isinstance(recent.get("open"), dict):
            for k, row in recent["open"].items():
                if isinstance(row, list) and len(row) == len(Q_FIELDS):
                    p.open[str(k)] = [int(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None for x in row]
        p._prune()
        return p

    def archive_data(self) -> dict[str, Any]:
        """The big store: all days. Written about once a day (and when the guard stops)."""
        self._changed.clear()
        return {"schema": SCHEMA, "devs": list(self.devs), "days": dict(self.days)}

    def recent_data(self) -> dict[str, Any]:
        """The small store: the last RECENT_DAYS days and the quarter hours still open. Written every 15 minutes at most."""
        keep = sorted(self.days)[-RECENT_DAYS:]
        return {"schema": SCHEMA, "devs": list(self.devs), "days": {d: self.days[d] for d in keep},
                "open": {k: list(v) for k, v in self.open.items()}}

    def archive_due(self) -> bool:
        """A day other than the newest changed: the big store should be written (it holds the days the small one drops)."""
        newest = max(self.days) if self.days else None
        return any(d != newest for d in self._changed)

    def days_count(self) -> int:
        return len(self.days)

    def runs_count(self) -> int:
        return sum(len(v["a"].split(";")) for v in self.days.values() if v.get("a"))

    def _prune(self) -> None:
        for d in sorted(self.days)[:-KEEP_DAYS]:
            del self.days[d]

    def _append(self, day: str, key: str, row: str) -> None:
        cur = self.days.setdefault(day, {})
        cur[key] = (cur[key] + ";" + row) if cur.get(key) else row
        self._changed.add(day)
        self._prune()

    # ---------- forecast log ----------

    def needs_forecast(self, quarter: datetime) -> bool:
        """Typical and high of this quarter hour still missing (asked only then, the forecast is not worked out every cycle)."""
        row = self.open.get(quarter.isoformat())
        return row is None or row[Q_TYP] is None or row[Q_HAUS_TYP] is None

    def quarter_tick(self, now: datetime, quarter: datetime, forecast_kw: float | None,
                     typ: float | None = None, hoch: float | None = None,
                     haus_typ: float | None = None, haus_hoch: float | None = None,
                     eingriff: bool = False, geschaetzt: bool = False) -> None:
        """One cycle within the running quarter hour: takes the projection at its marks, typical and high once, the flags."""
        elapsed = (now - quarter).total_seconds()
        if elapsed < 0 or elapsed >= 900:
            return
        key = quarter.isoformat()
        if key in self._closed:
            return
        row = self.open.setdefault(key, [None] * len(Q_FIELDS))
        if forecast_kw is not None:
            for i, m in enumerate(MARKS_S):
                if row[i] is None and m <= elapsed < m + MARK_WINDOW_S:
                    row[i] = _c(forecast_kw)
        for i, v in ((Q_TYP, typ), (Q_HOCH, hoch), (Q_HAUS_TYP, haus_typ), (Q_HAUS_HOCH, haus_hoch)):
            if row[i] is None and v is not None:
                row[i] = _c(v)
        flags = row[Q_FLAGS] or 0
        if eingriff:
            flags |= F_EINGRIFF
        if geschaetzt:
            flags |= F_GESCHAETZT
        row[Q_FLAGS] = flags or None

    def quarter_end(self, start: datetime, kw: float | None, geschaetzt: bool = False) -> bool:
        """The quarter hour from `start` has ended with `kw` (energy as kW): its row is written. False if it was written already."""
        key = start.isoformat()
        if key in self._closed:
            return False
        row = self.open.pop(key, None) or [None] * len(Q_FIELDS)
        row[Q_ENDE] = _c(kw)
        if geschaetzt:
            row[Q_FLAGS] = (row[Q_FLAGS] or 0) | F_GESCHAETZT
        self._close(start, row)
        return True

    def close_stale(self, now: datetime) -> bool:
        """Quarter hours whose end was not seen (Home Assistant stopped, no grid value at the end) are written without it."""
        done = False
        for key in list(self.open):
            try:
                start = datetime.fromisoformat(key)
            except ValueError:
                del self.open[key]
                continue
            if start.tzinfo is None and now.tzinfo is not None:
                start = start.replace(tzinfo=now.tzinfo)
            if (now - start).total_seconds() >= OPEN_MAX_S or (now - start).total_seconds() < -OPEN_MAX_S:
                row = self.open.pop(key)
                if any(v is not None for v in row[:Q_ENDE]):
                    self._close(start, row)
                    done = True
        return done

    def _close(self, start: datetime, row: list[int | None]) -> None:
        self._closed = (self._closed + [start.isoformat()])[-16:]
        self._append(start.strftime("%Y-%m-%d"), "q", str(_slot(start)) + ("," + _enc(row) if _enc(row) else ""))

    def rows(self, day: str) -> list[dict[str, Any]]:
        """The quarter hours of a day, in the order written (a repeated hour at the change of the clock appears twice)."""
        out = []
        text = (self.days.get(day) or {}).get("q") or ""
        for r in text.split(";") if text else []:
            head, _, rest = r.partition(",")
            try:
                slot = int(head)
            except ValueError:
                continue
            vals = _dec(rest, len(Q_FIELDS))
            d: dict[str, Any] = {"slot": slot, "zeit": f"{slot // 4:02d}:{slot % 4 * 15:02d}"}
            for name, v in zip(Q_FIELDS, vals):
                d[name] = (v or 0) if name == "flags" else (v / 100.0 if v is not None else None)
            out.append(d)
        return out

    # ---------- start log ----------

    def add_run(self, dev_id: str, run: dict[str, Any]) -> None:
        if dev_id not in self.devs:
            self.devs.append(dev_id)
        t0: datetime = run["start"]
        vals = [t0.hour * 60 + t0.minute] + [run.get(k) for k in A_FIELDS[1:]]
        self._append(t0.strftime("%Y-%m-%d"), "a", str(self.devs.index(dev_id)) + "," + _enc(vals))

    def runs(self, day: str) -> list[dict[str, Any]]:
        out = []
        text = (self.days.get(day) or {}).get("a") or ""
        for r in text.split(";") if text else []:
            vals = _dec(r, 1 + len(A_FIELDS))
            if vals[0] is None:
                continue
            d: dict[str, Any] = {"device": self.devs[vals[0]] if vals[0] < len(self.devs) else None}
            d.update({name: v for name, v in zip(A_FIELDS, vals[1:])})
            d["flags"] = d["flags"] or 0
            out.append(d)
        return out


class Anlauf:
    """Watches the power of every device and gives a finished start back from `sample` (else None). Only in memory: a start
    that runs while Home Assistant restarts is not recorded (after a start the first value above the threshold is no start)."""

    def __init__(self, voltage: float = 230.0) -> None:
        self.voltage = float(voltage)
        self.st: dict[str, dict[str, Any]] = {}

    def sample(self, dev_id: str, kind: str, now: datetime, power_w: float | None, current_a: float | None = None,
               phases: int | None = None, intervened: bool = False, changed: datetime | None = None,
               gap_s: float | None = None) -> dict[str, Any] | None:
        if kind not in START_W or power_w is None:
            return None
        st = self.st.setdefault(dev_id, {"below": None, "low_at": None, "run": None})
        on = power_w >= START_W[kind]
        run = st["run"]
        if run is not None:
            rel = (now - run["t0"]).total_seconds()
            if rel > WINDOW_S or rel < 0:
                st["run"] = None
                done = self._finish(run, kind, short=False)
                if not on:
                    st["below"], st["low_at"] = now, now
                return done
            if not on:
                st["run"] = None
                st["below"], st["low_at"] = now, now
                return self._finish(run, kind, short=True)
            self._add(run, rel, power_w, current_a, phases, intervened, gap_s)
            return None
        if not on:
            if st["below"] is None:
                st["below"] = now
            st["low_at"] = now
            return None
        below, low_at = st["below"], st["low_at"]
        st["below"] = None
        if below is None or low_at is None or (low_at - below).total_seconds() + CYCLE_S < OFF_S:
            return None   # first value after a start of the guard, or only a short dip: no new run
        t0 = changed if changed is not None and low_at < changed <= now else now
        run = st["run"] = {"t0": t0, "s": [], "tv": [], "iv": False, "gap": []}
        self._add(run, (now - t0).total_seconds(), power_w, current_a, phases, intervened, gap_s)
        return None

    def _add(self, run: dict[str, Any], rel: float, w: float, current_a: float | None, phases: int | None,
             intervened: bool, gap_s: float | None) -> None:
        run["s"].append((rel, float(w)))
        run["tv"].append((float(current_a), int(phases) if phases else None) if current_a and current_a > 0 else None)
        run["iv"] = run["iv"] or bool(intervened)
        if gap_s is not None:
            run["gap"].append(float(gap_s))

    def _finish(self, run: dict[str, Any], kind: str, short: bool) -> dict[str, Any] | None:
        s = run["s"]
        if not s:
            return None
        early = [w for rel, w in s if rel <= PEAK_S]
        steady = [w for rel, w in s if rel >= STEADY_FROM_S]
        if not steady:   # a short run: its last third
            last = s[-1][0]
            steady = [w for rel, w in s if rel >= last * 2.0 / 3.0]
        dauer = median(steady)
        band = max(BAND_MIN_W, BAND_SHARE * dauer)
        stabil = None
        for k in range(len(s) - 1, -1, -1):
            if abs(s[k][1] - dauer) > band:
                break
            stabil = s[k][0]
        vorgabe = None
        if kind in ("wallbox", "evcc"):
            for (rel, w), tv in zip(s, run["tv"]):
                if tv is None:
                    continue
                amps, ph = tv
                if not ph:   # phases not known: what the steady power says (more than 1.5 phases worth = three)
                    ph = 3 if dauer > 1.5 * amps * self.voltage else 1
                if w >= TARGET_SHARE * amps * ph * self.voltage:
                    vorgabe = rel
                    break
        gap = median(run["gap"]) if run["gap"] else None
        flags = (A_EINGRIFF if run["iv"] else 0) | (A_KURZ if short else 0) | (A_GROB if gap is not None and gap >= COARSE_GAP_S else 0)
        return {"start": run["t0"], "spitze_w": int(round(max(early or [s[0][1]]))), "dauer_w": int(round(dauer)),
                "stabil_s": int(round(stabil)) if stabil is not None else None,
                "vorgabe_s": int(round(vorgabe)) if vorgabe is not None else None,
                "abstand_s": int(round(gap)) if gap is not None else None, "flags": flags}
