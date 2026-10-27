"""Switches for the optional features. All default to ON; the last state is restored after a restart."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import WaechterEntry
from .entity import WaechterEntity


async def async_setup_entry(hass: HomeAssistant, entry: WaechterEntry, add: AddEntitiesCallback) -> None:
    w = entry.runtime_data
    add([
        FeatureSwitch(w, "paid_peak", "paid_peak", "mdi:cash-check"),
        FeatureSwitch(w, "notify_intervention", "notify_intervention", "mdi:bell-ring"),
        FeatureSwitch(w, "costs_enabled", "costs_enabled", "mdi:currency-eur"),
        FeatureSwitch(w, "forecast_enabled", "forecast_enabled", "mdi:chart-timeline-variant"),
        OffByDefaultSwitch(w, "predictive", "predictive", "mdi:crystal-ball"),
        OffByDefaultSwitch(w, "battery_reserve", "battery_reserve", "mdi:battery-lock"),
        ExecuteSwitch(w, "ai_explainer", "ai_explainer", "mdi:robot-outline"),
        OffByDefaultSwitch(w, "prewarn", "prewarn", "mdi:bell-alert-outline"),
        FeatureSwitch(w, "weekly_report_enabled", "weekly_enabled", "mdi:calendar-week"),
        FeatureSwitch(w, "charge_plan_enabled", "plan_enabled", "mdi:ev-station"),
        ExecuteSwitch(w, "charge_plan_execute", "plan_execute", "mdi:play-circle-outline"),
    ])


class FeatureSwitch(WaechterEntity, SwitchEntity, RestoreEntity):
    def __init__(self, w, key: str, attr: str, icon: str) -> None:
        super().__init__(w, key)
        self._attr = attr
        self._attr_icon = icon

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        setattr(self.waechter, self._attr, last is None or last.state != "off")  # default on

    @property
    def is_on(self) -> bool:
        return bool(getattr(self.waechter, self._attr))

    async def async_turn_on(self, **kwargs) -> None:
        setattr(self.waechter, self._attr, True)
        self.async_write_ha_state()
        await self.waechter.async_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        setattr(self.waechter, self._attr, False)
        self.async_write_ha_state()
        await self.waechter.async_refresh()


class OffByDefaultSwitch(FeatureSwitch):
    """An optional feature that is off until it is switched on; the last state is restored after a restart."""

    async def async_added_to_hass(self) -> None:
        await WaechterEntity.async_added_to_hass(self)
        last = await self.async_get_last_state()
        setattr(self.waechter, self._attr, last is not None and last.state == "on")


class ExecuteSwitch(FeatureSwitch):
    """Always OFF after a restart: carry out the charge plan (a plan that pauses charging must be switched on on
    purpose; turning it off lets the car charge normally again) and the AI explainer (it may cost money)."""

    async def async_added_to_hass(self) -> None:
        await WaechterEntity.async_added_to_hass(self)
        setattr(self.waechter, self._attr, False)
