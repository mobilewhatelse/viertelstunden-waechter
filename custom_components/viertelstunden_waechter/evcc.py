"""evcc as a wallbox of the guard (talks to evcc's REST API directly; no other integration needed).

Why a ceiling and not the current itself: evcc regulates the charging current continuously (sun, minimum current, plans). The guard sets
evcc's **maximum current** of the loadpoint, a ceiling that evcc respects, and gives it back afterwards. evcc stays in charge of everything
below the ceiling.

What the guard works with ("virtual current"): while the car charges, a reduction has to go below what evcc *offers* right now, not below
the ceiling (a ceiling of 16 A does nothing while evcc offers 8 A). So the guard sees `min(ceiling, offered)`. For the take-back it needs
the **original ceiling**, which is remembered when the first reduction starts (`target_ceiling`).

Pure Python except for the client, which only needs an object with aiohttp's `request` (so it can be tested with a fake).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

TIMEOUT_S = 6.0


class EvccError(Exception):
    """evcc could not be reached or answered with an error."""


class EvccAuthError(EvccError):
    """evcc wants a password (or the password was refused)."""


def normalize_url(url: str) -> str:
    u = (url or "").strip().rstrip("/")
    if u and "://" not in u:
        u = "http://" + u
    return u


def _num(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def parse_loadpoint(state: dict[str, Any] | None, loadpoint: int) -> dict[str, Any] | None:
    """The fields the guard needs of loadpoint number `loadpoint` (1 = first), or None if it does not exist."""
    lps = (state or {}).get("loadpoints")
    if not isinstance(lps, list) or loadpoint < 1 or loadpoint > len(lps) or not isinstance(lps[loadpoint - 1], dict):
        return None
    lp = lps[loadpoint - 1]
    pa, pc = _num(lp.get("phasesActive")), _num(lp.get("phasesConfigured"))
    return {
        "title": lp.get("title") or lp.get("name") or f"#{loadpoint}",
        "mode": lp.get("mode"),
        "connected": bool(lp.get("connected")),
        "charging": bool(lp.get("charging")),
        "power_w": _num(lp.get("chargePower")),
        "ceiling": _num(lp.get("maxCurrent")),
        "min_current": _num(lp.get("minCurrent")),
        "offered": _num(lp.get("offeredCurrent")),
        "phases_active": int(pa) if pa is not None else None,
        "phases_configured": int(pc) if pc is not None else None,
        "phases_switchable": bool(lp.get("chargerPhases1p3p")),
        "heating": bool(lp.get("chargerFeatureHeating")),
    }


def virtual_current(lp: dict[str, Any] | None) -> float | None:
    """The current the guard works with: what evcc offers while the car charges (never above the ceiling), else the ceiling."""
    if not lp or lp.get("ceiling") is None:
        return None
    ceiling, offered = float(lp["ceiling"]), lp.get("offered")
    if lp.get("charging") and offered and float(offered) > 0:
        return min(ceiling, float(offered))
    return ceiling


def target_ceiling(value: float, orig: dict[str, float] | None) -> tuple[int, bool]:
    """The ceiling to set for the guard's wish `value` (A), and whether this takes everything back.

    `orig` = {"ceiling", "virtual"} remembered when the reduction began. A wish at or above the virtual current of that moment means
    "back to normal": the original ceiling is restored (not the lower value that the guard saw)."""
    if orig and value >= float(orig["virtual"]) - 1e-9:
        return int(round(float(orig["ceiling"]))), True
    return int(round(value)), False


class EvccClient:
    """Reads the state and sets ceiling and phases. With a password it logs in itself and again when the login has run out."""

    def __init__(self, session: Any, url: str, password: str | None = None, timeout: float = TIMEOUT_S) -> None:
        self._session = session
        self._base = normalize_url(url)
        self._password = password or ""
        self._timeout = timeout
        self._cookie: str | None = None

    async def _login(self) -> None:
        try:
            async with asyncio.timeout(self._timeout):
                async with self._session.request("POST", self._base + "/api/auth/login", json={"password": self._password}) as resp:
                    if resp.status in (400, 401, 403):
                        raise EvccAuthError("login refused")
                    if resp.status >= 400:
                        raise EvccError(f"login answered {resp.status}")
                    cookie = resp.cookies.get("auth")
                    self._cookie = getattr(cookie, "value", cookie)
        except EvccError:
            raise
        except Exception as err:  # noqa: BLE001
            raise EvccError(str(err) or type(err).__name__) from err

    async def _request(self, method: str, path: str, retry: bool = True) -> Any:
        headers = {"Cookie": f"auth={self._cookie}"} if self._cookie else {}
        try:
            async with asyncio.timeout(self._timeout):
                async with self._session.request(method, self._base + path, headers=headers) as resp:
                    status = resp.status
                    text = await resp.text()
                    ctype = str(getattr(resp, "content_type", "") or "")
        except Exception as err:  # noqa: BLE001
            raise EvccError(str(err) or type(err).__name__) from err
        if status == 401:
            if self._password and retry:
                await self._login()
                return await self._request(method, path, retry=False)
            raise EvccAuthError("evcc wants a password" if not self._password else "password refused")
        if status >= 400:
            raise EvccError(f"evcc answered {status}: {text[:120]}")
        if "json" in ctype or text[:1] in "{[":
            try:
                return json.loads(text)
            except ValueError:
                return text
        return text

    async def check_password(self) -> None:
        """evcc answers /api/state without a login, so a wrong password would only show at the first intervention. With a password
        entered, log in once: raises EvccAuthError if evcc refuses it. Anything else (no login on this evcc) is not an error here."""
        if not self._password:
            return
        try:
            await self._login()
        except EvccAuthError:
            raise
        except EvccError:
            return

    async def state(self) -> dict[str, Any]:
        data = await self._request("GET", "/api/state")
        if not isinstance(data, dict):
            raise EvccError("unexpected answer of /api/state")
        return data.get("result", data) if isinstance(data.get("result"), dict) else data

    async def set_max_current(self, loadpoint: int, amps: int) -> None:
        await self._request("POST", f"/api/loadpoints/{int(loadpoint)}/maxcurrent/{int(amps)}")

    async def set_phases(self, loadpoint: int, phases: int) -> None:
        await self._request("POST", f"/api/loadpoints/{int(loadpoint)}/phases/{int(phases)}")


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
    """True if two readings of the grid IMPORT differ clearly (absolute and relative); a missing reading is no difference.
    Export counts as 0 on both sides, as it does for the guard: an import-only sensor (0 while exporting) and a signed one
    (negative while exporting) agree then."""
    if a_kw is None or b_kw is None:
        return False
    a_kw, b_kw = max(0.0, a_kw), max(0.0, b_kw)
    diff = abs(a_kw - b_kw)
    return diff > SOURCES_DIFFER_ABS_KW and diff > SOURCES_DIFFER_REL * max(abs(a_kw), abs(b_kw))
