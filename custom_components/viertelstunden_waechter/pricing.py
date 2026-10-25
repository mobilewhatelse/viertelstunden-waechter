"""Cost of the monthly peak under a power-based grid tariff (pure Python)."""

from __future__ import annotations


def monthly_cost(peak_kw: float, price_low: float, price_high: float, threshold_kw: float) -> float:
    """Cost for one month. Prices are per kW and year; the monthly peak is billed with one twelfth.

    The first `threshold_kw` of the peak cost `price_low`, the part above costs `price_high`.
    """
    peak = max(0.0, peak_kw)
    return (min(peak, threshold_kw) * price_low + max(peak - threshold_kw, 0.0) * price_high) / 12.0
