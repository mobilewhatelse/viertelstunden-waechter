"""Numbers: limit and safety margin in kW."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberMode, RestoreNumber
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import WaechterEntry
from .entity import WaechterEntity


async def async_setup_entry(hass: HomeAssistant, entry: WaechterEntry, add: AddEntitiesCallback) -> None:
    w = entry.runtime_data
    add([KwNumber(w, "limit", "limit_kw", 1.0, 50.0), KwNumber(w, "margin", "margin_kw", 0.0, 5.0)])


class KwNumber(WaechterEntity, RestoreNumber):
    _attr_mode = NumberMode.BOX
    _attr_native_step = 0.1
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
    _attr_device_class = NumberDeviceClass.POWER

    def __init__(self, w, key: str, attr: str, lo: float, hi: float) -> None:
        super().__init__(w, key)
        self._attr = attr
        self._attr_native_min_value = lo
        self._attr_native_max_value = hi

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            setattr(self.waechter, self._attr, float(last.native_value))

    @property
    def native_value(self) -> float:
        return getattr(self.waechter, self._attr)

    async def async_set_native_value(self, value: float) -> None:
        setattr(self.waechter, self._attr, float(value))
        self.async_write_ha_state()
