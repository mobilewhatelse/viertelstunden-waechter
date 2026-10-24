"""Selects: operating mode (off / observe / active) and strategy."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import WaechterEntry
from .const import CONF_STARTUP_MODE, MODE_OBSERVE, MODES, STARTUP_RESTORE
from .engine import STRATEGY_COMFORT, STRATEGY_ORDER
from .entity import WaechterEntity


async def async_setup_entry(hass: HomeAssistant, entry: WaechterEntry, add: AddEntitiesCallback) -> None:
    w = entry.runtime_data
    add([ModeSelect(w), StrategySelect(w)])


class ModeSelect(WaechterEntity, SelectEntity, RestoreEntity):
    _attr_options = MODES
    _attr_icon = "mdi:shield-sync"

    def __init__(self, w) -> None:
        super().__init__(w, "mode")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        startup = self.waechter.cfg.get(CONF_STARTUP_MODE, STARTUP_RESTORE)
        mode = MODE_OBSERVE
        if startup == STARTUP_RESTORE:
            last = await self.async_get_last_state()
            if last is not None and last.state in MODES:
                mode = last.state
        elif startup in MODES:
            mode = startup
        self.waechter.mode = mode

    @property
    def current_option(self) -> str:
        return self.waechter.mode

    async def async_select_option(self, option: str) -> None:
        await self.waechter.async_set_mode(option)
        self.async_write_ha_state()


class StrategySelect(WaechterEntity, SelectEntity, RestoreEntity):
    _attr_options = [STRATEGY_COMFORT, STRATEGY_ORDER]
    _attr_icon = "mdi:sort-variant"

    def __init__(self, w) -> None:
        super().__init__(w, "strategy")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in self._attr_options:
            self.waechter.guard.strategy = last.state

    @property
    def current_option(self) -> str:
        return self.waechter.guard.strategy

    async def async_select_option(self, option: str) -> None:
        self.waechter.guard.strategy = option
        self.async_write_ha_state()
