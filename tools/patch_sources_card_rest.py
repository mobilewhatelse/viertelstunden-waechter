"""One-off: second half of patch_sources_card.py (first half had run; kept for the record)."""

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


edit("dashboard.py", [
    ('''        "now": "Jetzt", "costs": "Kosten und Ersparnis",''', '''        "src_title": "Quellen im Vergleich", "src_own": "Ihr Sensor", "src_evcc": "evcc", "src_counts": "es gilt",
        "src_reserve": "Reserve", "src_differ": "Ihr Sensor und evcc zeigen deutlich verschiedenen Bezug. Der Wächter regelt mit Ihrem Sensor.",
        "src_twice": "Eine Wallbox scheint doppelt eingetragen (als Wallbox und als evcc-Ladepunkt).", "src_down": "evcc liefert gerade keinen Netzbezug.",
        "now": "Jetzt", "costs": "Kosten und Ersparnis",'''),
    ('''        "now": "Now", "costs": "Cost and savings",''', '''        "src_title": "Sources compared", "src_own": "Your sensor", "src_evcc": "evcc", "src_counts": "counts now",
        "src_reserve": "reserve", "src_differ": "Your sensor and evcc show clearly different import. The guard works with your sensor.",
        "src_twice": "A wallbox seems to be entered twice (as wallbox and as evcc loadpoint).", "src_down": "evcc is not delivering a grid import right now.",
        "now": "Now", "costs": "Cost and savings",'''),
    ('''def build_views(ids: dict[str, str], lang: str = "en", planners: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:''',
     '''def build_views(ids: dict[str, str], lang: str = "en", planners: list[dict[str, Any]] | None = None,
                evcc: bool = False) -> list[dict[str, Any]]:'''),
    ('''                _tile(ids["today_peak"], x["peak_today"]), _tile(ids["month_peak"], x["peak_month"]),
                _tile(ids["interventions_today"], x["iv_today"]),
            ]},''', '''                _tile(ids["today_peak"], x["peak_today"]), _tile(ids["month_peak"], x["peak_month"]),
                _tile(ids["interventions_today"], x["iv_today"]),
            ] + ([{"type": "markdown", "content": charts.sources(ids, x["src_title"], x["src_own"], x["src_evcc"], x["src_counts"],
                                                            x["src_reserve"], x["src_differ"], x["src_twice"], x["src_down"])}] if evcc else [])},'''),
])

edit("__init__.py", [(
    '''    config = {"views": build_views(ids, hass.config.language, _planners(hass, entries[0]))}''',
    '''    cfg = {**entries[0].data, **entries[0].options}
    if cfg.get("grid_power"):
        ids["grid_power_sensor"] = cfg["grid_power"]
    config = {"views": build_views(ids, hass.config.language, _planners(hass, entries[0]), evcc=bool(cfg.get("evcc_site_url")))}''')])
print("ok")
