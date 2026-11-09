"""One-off: card 'Sources compared' in the generated dashboard, only when evcc is entered (kept for the record).

User 2026-11-09: shipped with the integration, but visible only with an evcc address in the settings. A small chart: your sensor and evcc
as two bars of the grid import, which one counts now, and a warning line when they differ or a wallbox seems to be entered twice.
"""
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


edit("dashboard_charts.py", [("def now_bar(", '''def sources(ids: dict[str, str], title: str, own: str, evcc: str, counts: str, reserve: str, differ: str, twice: str, down: str) -> str:
    """The grid import from your sensor and from evcc as two bars, which source counts now, and warnings. Export counts as 0."""
    return _fill(
        "{% set a = states['@ST@'].attributes if states['@ST@'] is defined else {} %}"
        "{% set src = a.get('grid_source') %}{% set e = a.get('grid_evcc_kw') %}"
        "{% set s = states('@GP@') | float(none) if '@GP@' else none %}{% set su = state_attr('@GP@', 'unit_of_measurement') if '@GP@' else none %}"
        "{% if s is not none and su == 'W' %}{% set s = s / 1000 %}{% elif s is not none and su == 'MW' %}{% set s = s * 1000 %}{% endif %}"
        "{% set sv = [s or 0, 0] | max %}{% set ev = [e or 0, 0] | max %}{% set vmax = [[sv, ev] | max * 1.2, 1] | max %}"
        "{% set W = 720 %}{% set L = 150 %}{% set R = 90 %}{% set bw = W - L - R %}"
        "{% set g = \\"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 720 104' font-family='Roboto,Arial,sans-serif' font-size='13'>"
        "<text x='12' y='34' fill='@GREY@'>@OWN@</text>"
        "<rect x='\\" ~ L ~ \\"' y='20' width='\\" ~ bw ~ \\"' height='20' rx='10' fill='@GREY@' fill-opacity='0.2'/>"
        "<rect x='\\" ~ L ~ \\"' y='20' width='\\" ~ ([sv / vmax * bw, 4] | max if s is not none else 0) ~ \\"' height='20' rx='10' fill='\\" ~ ('@BLUE@' if src == 'sensor' else '@GREY@') ~ \\"'/>"
        "<text x='\\" ~ (W - 12) ~ \\"' y='35' text-anchor='end' fill='@GREY@'>\\" ~ (('%.2f' | format(sv)) ~ ' kW' if s is not none else '–') ~ \\"</text>"
        "<text x='12' y='78' fill='@GREY@'>@EVCC@</text>"
        "<rect x='\\" ~ L ~ \\"' y='64' width='\\" ~ bw ~ \\"' height='20' rx='10' fill='@GREY@' fill-opacity='0.2'/>"
        "<rect x='\\" ~ L ~ \\"' y='64' width='\\" ~ ([ev / vmax * bw, 4] | max if e is not none else 0) ~ \\"' height='20' rx='10' fill='\\" ~ ('@BLUE@' if src == 'evcc' else '@GREY@') ~ \\"'/>"
        "<text x='\\" ~ (W - 12) ~ \\"' y='79' text-anchor='end' fill='@GREY@'>\\" ~ (('%.2f' | format(ev)) ~ ' kW' if e is not none else '–') ~ \\"</text>"
        "</svg>\\" %}"
        "**@TITLE@** · @COUNTS@: {{ '@OWN@' if src == 'sensor' else ('@EVCC@ (@RESERVE@)' if src == 'evcc' and '@GP@' else ('@EVCC@' if src == 'evcc' else '–')) }}\\n\\n"
        "![](data:image/svg+xml;utf8,{{ g | urlencode }})"
        "{% if e is none %}\\n\\n@DOWN@{% endif %}"
        "{% if a.get('sources_differ') %}\\n\\n⚠️ @DIFFER@{% endif %}"
        "{% if a.get('wallbox_twice') %}\\n\\n⚠️ @TWICE@ ({{ a.get('wallbox_twice') }}){% endif %}",
        ST=ids["status"], GP=ids.get("grid_power_sensor", ""), TITLE=title, OWN=own, EVCC=evcc, COUNTS=counts, RESERVE=reserve,
        DIFFER=differ, TWICE=twice, DOWN=down, GREY=GREY, BLUE=BLUE,
    )


def now_bar(''')])

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
    ('''                _tile(ids["interventions_today"], x["iv_today"]),
            ]},''', '''                _tile(ids["interventions_today"], x["iv_today"]),
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
