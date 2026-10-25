"""Sensors: status, running quarter hour, last quarter hour, month peak, interventions."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import WaechterEntry
from .const import STATUS_OPTIONS
from .entity import WaechterEntity


async def async_setup_entry(hass: HomeAssistant, entry: WaechterEntry, add: AddEntitiesCallback) -> None:
    w = entry.runtime_data
    add([
        StatusSensor(w),
        ValueSensor(w, "quarter_energy", "quarter_energy_kwh", UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, 3),
        ValueSensor(w, "forecast", "forecast_kw", UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, 2),
        ValueSensor(w, "allowed", "allowed_kw", UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, 2),
        ValueSensor(w, "saved_now", "saved_kw", UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, 2),
        CostSensor(w, "cost_month", "cost"),
        CostSensor(w, "cost_without", "cost_without"),
        CostSensor(w, "savings_month", "saving"),
        SavingsYearSensor(w),
        LastQuarterSensor(w),
        TodayPeakSensor(w),
        MonthPeakSensor(w),
        InterventionsTodaySensor(w),
    ])


class StatusSensor(WaechterEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATUS_OPTIONS
    _attr_icon = "mdi:shield-half-full"

    def __init__(self, w) -> None:
        super().__init__(w, "status")

    @property
    def native_value(self) -> str:
        return self.waechter.status

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        w = self.waechter
        return {
            "mode": w.mode,
            "interventions": w.intervention_names(),
            "recent": w.log_lines(10),
            "today": w.log_lines(50, today_only=True),
            "room_kw": w.guard.values.get("room_kw"),
            "target_kw": w.guard.values.get("target_kw"),
            "configuration": w.configuration(),
        }


class ValueSensor(WaechterEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, w, key: str, value_key: str, unit: str, device_class, digits: int) -> None:
        super().__init__(w, key)
        self._value_key = value_key
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_suggested_display_precision = digits
        if device_class == SensorDeviceClass.ENERGY:
            self._attr_state_class = SensorStateClass.TOTAL  # restarts every quarter hour

    @property
    def native_value(self) -> float | None:
        return self.waechter.guard.values.get(self._value_key)

    @property
    def last_reset(self):
        return self.waechter.guard.values.get("quarter") if self._value_key == "quarter_energy_kwh" else None


class CostSensor(WaechterEntity, SensorEntity):
    """Cost of this month's peak with the guard, without it (estimate) or the difference. Needs the prices."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR"
    _attr_suggested_display_precision = 2

    def __init__(self, w, key: str, field: str) -> None:
        super().__init__(w, key)
        self._field = field

    @property
    def native_value(self) -> float | None:
        return self.waechter.month_costs(dt_util.now().strftime("%Y-%m"))[self._field]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        c = self.waechter.month_costs(dt_util.now().strftime("%Y-%m"))
        return {"peak_kw": c["peak"], "peak_without_kw": c["peak_without"], "prices_set": self.waechter.prices_set}


class SavingsYearSensor(WaechterEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR"
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:piggy-bank"

    def __init__(self, w) -> None:
        super().__init__(w, "savings_year")

    @property
    def native_value(self) -> float | None:
        return self.waechter.year_saving(dt_util.now().strftime("%Y"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        w = self.waechter
        year = dt_util.now().strftime("%Y")
        return {"months": {m: w.month_costs(m)["saving"] for m in sorted(w.months) if m.startswith(year)}}


class LastQuarterSensor(WaechterEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
    _attr_suggested_display_precision = 2

    def __init__(self, w) -> None:
        super().__init__(w, "last_quarter")

    @property
    def native_value(self) -> float | None:
        return self.waechter.last_quarter_kw


class TodayPeakSensor(WaechterEntity, SensorEntity):
    """Highest quarter hour today; attribute `days` lists the peaks of the last 31 days (for a table or chart)."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:calendar-today"

    def __init__(self, w) -> None:
        super().__init__(w, "today_peak")

    @property
    def native_value(self) -> float:
        return float(self.waechter.day_peaks.get(dt_util.now().strftime("%Y-%m-%d"), {}).get("kw") or 0.0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        w = self.waechter
        days = [{"date": d, **w.day_peaks[d]} for d in sorted(w.day_peaks, reverse=True)[:31]]
        return {"days": days, "days_over_limit": sum(1 for x in days if x["kw"] > w.limit_kw)}


class MonthPeakSensor(WaechterEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:chart-bell-curve-cumulative"

    def __init__(self, w) -> None:
        super().__init__(w, "month_peak")

    @property
    def native_value(self) -> float | None:
        mp = self.waechter.month_peak
        if not mp or mp.get("month") != dt_util.now().strftime("%Y-%m"):
            return 0.0 if mp else None
        return mp.get("kw")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"month": self.waechter.month_peak.get("month"), "quarter_start": self.waechter.month_peak.get("at")}


class InterventionsTodaySensor(WaechterEntity, SensorEntity):
    _attr_icon = "mdi:counter"

    def __init__(self, w) -> None:
        super().__init__(w, "interventions_today")

    @property
    def native_value(self) -> int:
        day = self.waechter.counts.get(dt_util.now().strftime("%Y-%m-%d"), {})
        return int(day.get("real", 0))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        day = self.waechter.counts.get(dt_util.now().strftime("%Y-%m-%d"), {})
        return {"observed": int(day.get("shadow", 0))}
