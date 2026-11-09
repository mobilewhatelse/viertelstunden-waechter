"""One-off: evcc as a wallbox of the guard, core part (constants, engine kind, coordinator) (kept for the record)."""
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


edit("const.py", [(
    'D_ID = "id"\n',
    'D_ID = "id"\nD_EVCC_URL = "evcc_url"                # evcc: address, e.g. http://192.168.1.20:7070\n'
    'D_EVCC_LOADPOINT = "evcc_loadpoint"    # evcc: number of the loadpoint (1 = first)\n'
    'D_EVCC_PASSWORD = "evcc_password"      # evcc: password, only if evcc asks for one\n'
    'D_EVCC_ONE_PHASE = "evcc_one_phase"    # evcc: the guard may switch the loadpoint to 1 phase (if the charger can)\n',
)])

edit("engine.py", [(
    'KIND_WALLBOX = "wallbox"\n',
    'KIND_WALLBOX = "wallbox"\nKIND_EVCC = "evcc"          # a wallbox behind evcc: the guard sets evcc\'s ceiling of the loadpoint, otherwise a wallbox\nWALLBOX_KINDS = (KIND_WALLBOX, KIND_EVCC)\n',
)])

edit("coordinator.py", [
    ("from .explain import build_instructions, extract_text, plain_summary\n",
     "from .const import D_EVCC_LOADPOINT, D_EVCC_ONE_PHASE, D_EVCC_PASSWORD, D_EVCC_URL\n"
     "from .evcc import EvccClient, parse_loadpoint, target_ceiling, virtual_current\n"
     "from .explain import build_instructions, extract_text, plain_summary\n"),
    ("    DeviceConfig, Guard, Reading,\n)\n", "    DeviceConfig, Guard, Reading, KIND_EVCC, WALLBOX_KINDS,\n)\n"),
    ('''        self.guard = Guard(
            [DeviceConfig.from_dict(d) for d in self.raw_devices.values() if d[D_KIND] != KIND_VEHICLE], STRATEGY_COMFORT,''',
     '''        self._evcc_lp: dict[str, dict[str, Any] | None] = {}   # device id -> loadpoint as read from evcc (None = not reachable)
        self._evcc_orig: dict[str, dict[str, float]] = {}      # device id -> ceiling and virtual current when a reduction began
        self._evcc_clients: dict[tuple[str, str], EvccClient] = {}
        self._evcc_down: set[tuple[str, str]] = set()
        self.guard = Guard(
            [DeviceConfig.from_dict(self._engine_dict(d)) for d in self.raw_devices.values() if d[D_KIND] != KIND_VEHICLE], STRATEGY_COMFORT,'''),
    ('''            r.power_w = p * 1000.0 if p is not None else None
            kind = d[D_KIND]
            if kind == KIND_WALLBOX:''', '''            r.power_w = p * 1000.0 if p is not None else None
            kind = d[D_KIND]
            if kind == KIND_EVCC:
                lp = self._evcc_lp.get(dev_id)
                if p is None and lp:
                    r.power_w = lp["power_w"]
                r.current_a = virtual_current(lp)
                r.available = r.current_a is not None
                if lp:
                    r.phases = lp["phases_active"]
                    if d.get(D_EVCC_ONE_PHASE) and lp["phases_switchable"] and lp["phases_configured"] is not None:
                        r.phase_option = str(lp["phases_configured"])
            elif kind == KIND_WALLBOX:'''),
    ('''            now = dt_util.now()
            readings = self._readings()
            locked = self._is_on(self.cfg.get(CONF_LOCK), False)''', '''            now = dt_util.now()
            await self._poll_evcc()
            readings = self._readings()
            locked = self._is_on(self.cfg.get(CONF_LOCK), False)'''),
    ('''        self._battery_orig = data.get("battery_orig", {})
''', '''        self._battery_orig = data.get("battery_orig", {})
        self._evcc_orig = data.get("evcc_orig", {})
'''),
    ('''            self.guard.load({"interventions": data["interventions"]})
            await self._run(''', '''            self.guard.load({"interventions": data["interventions"]})
            await self._poll_evcc()
            await self._run('''),
    ('''            "battery_orig": self._battery_orig,
''', '''            "battery_orig": self._battery_orig,
            "evcc_orig": self._evcc_orig,
'''),
    ('''    async def _exec(self, a: Action) -> None:
        d = self.raw_devices.get(a.device_id, {})
        if a.kind == "set_current":''', '''    @staticmethod
    def _engine_dict(d: dict[str, Any]) -> dict[str, Any]:
        """What the engine gets of a device: an evcc loadpoint is a wallbox for it (one-phase option is the number of phases)."""
        if d.get(D_KIND) != KIND_EVCC:
            return d
        return {**d, D_KIND: KIND_WALLBOX, "one_phase_option": "1" if d.get(D_EVCC_ONE_PHASE) else None}

    def _evcc_client(self, url: str, password: str) -> EvccClient:
        key = (url, password)
        if key not in self._evcc_clients:
            self._evcc_clients[key] = EvccClient(async_get_clientsession(self.hass), url, password)
        return self._evcc_clients[key]

    async def _poll_evcc(self) -> None:
        """Read evcc once per address and keep the loadpoints of the devices (unreachable = None: the guard leaves the device alone)."""
        states: dict[tuple[str, str], dict[str, Any] | None] = {}
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

    async def _evcc_exec(self, a: Action, d: dict[str, Any]) -> None:
        client = self._evcc_client(str(d.get(D_EVCC_URL) or ""), str(d.get(D_EVCC_PASSWORD) or ""))
        loadpoint = int(d.get(D_EVCC_LOADPOINT) or 1)
        if a.kind == "set_phase":
            await client.set_phases(loadpoint, int(float(a.value)))
            return
        lp = self._evcc_lp.get(a.device_id)
        orig = self._evcc_orig.get(a.device_id)
        if orig is None and a.intervention and lp and lp.get("ceiling") is not None:
            orig = {"ceiling": float(lp["ceiling"]), "virtual": float(virtual_current(lp) or lp["ceiling"])}
            self._evcc_orig[a.device_id] = orig
        amps, restored = target_ceiling(float(a.value), orig)
        await client.set_max_current(loadpoint, amps)
        if restored:
            self._evcc_orig.pop(a.device_id, None)

    async def _exec(self, a: Action) -> None:
        d = self.raw_devices.get(a.device_id, {})
        if d.get(D_KIND) == KIND_EVCC and a.kind in ("set_current", "set_phase"):
            await self._evcc_exec(a, d)
        elif a.kind == "set_current":'''),
    ("        return any(d[D_KIND] == KIND_WALLBOX for d in self.raw_devices.values())",
     "        return any(d[D_KIND] in WALLBOX_KINDS for d in self.raw_devices.values())"),
    ("                if self.raw_devices.get(dev_id, {}).get(D_KIND) == KIND_WALLBOX) / 1000.0",
     "                if self.raw_devices.get(dev_id, {}).get(D_KIND) in WALLBOX_KINDS) / 1000.0"),
])

# the shared aiohttp session
edit("coordinator.py", [("from homeassistant.util import dt as dt_util\n",
                         "from homeassistant.helpers.aiohttp_client import async_get_clientsession\nfrom homeassistant.util import dt as dt_util\n")])
print("ok")
