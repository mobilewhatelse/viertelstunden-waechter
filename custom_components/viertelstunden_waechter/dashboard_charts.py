"""Charts for the generated dashboard as inline SVG images (pure Python, no Home Assistant imports).

A markdown card renders `![](data:image/svg+xml;utf8,...)`, so the charts need no custom card. The SVG is built by a
template from the sensors' attributes (forecast hours, weekly profile, daily peaks, months); colours are mid-tones that
read on light and dark themes. Every function returns the content of a markdown card.
"""

from __future__ import annotations

GREY = "#8a97a8"
BLUE = "#5b8fd6"
RED = "#e57373"


def _fill(template: str, **values: str) -> str:
    for key, value in values.items():
        template = template.replace(f"@{key}@", value)
    return template.strip()


def _axis(vmax_expr: str = "ns.vmax") -> str:
    """Horizontal grid lines with value labels at 0 / 25 / 50 / 75 / 100 % of the maximum."""
    return (
        "{% for k in range(0, 5) %}{% set yy = T + ph - ph * k / 4 %}"
        "{% set ns.g = ns.g ~ \"<line x1='\" ~ L ~ \"' x2='\" ~ (W - R) ~ \"' y1='\" ~ yy ~ \"' y2='\" ~ yy ~ \"' stroke='@GREY@' stroke-opacity='0.25'/>"
        "<text x='\" ~ (L - 6) ~ \"' y='\" ~ (yy + 4) ~ \"' text-anchor='end' fill='@GREY@'>\" ~ ('%.0f' | format(" + vmax_expr + " * k / 4)) ~ \"</text>\" %}{% endfor %}"
    ).replace("@GREY@", GREY)


def _limit_line(target_expr: str, label: str) -> str:
    return (
        "{% set ty0 = T + ph - " + target_expr + " / ns.vmax * ph %}"
        "{% set ns.g = ns.g ~ \"<line x1='\" ~ L ~ \"' x2='\" ~ (W - R) ~ \"' y1='\" ~ ty0 ~ \"' y2='\" ~ ty0 ~ \"' stroke='@RED@' stroke-width='2' stroke-dasharray='6 4'/>"
        "<text x='\" ~ (W - R - 4) ~ \"' y='\" ~ (ty0 - 5) ~ \"' text-anchor='end' fill='@RED@' font-weight='700' stroke='#1b2a41' stroke-width='3' paint-order='stroke'>" + label + " \" ~ ('%.1f' | format(" + target_expr + ")) ~ \" kW</text>\" %}"
    ).replace("@RED@", RED)


SVG_OPEN = ("{% set ns.g = \"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 720 @H@' "
            "font-family='Roboto,Arial,sans-serif' font-size='12'>\" %}")
SVG_IMAGE = "![](data:image/svg+xml;utf8,{{ ns.g | urlencode }})"


def forecast(ids: dict[str, str], target_label: str, legend: str, none_text: str) -> str:
    """24 hours ahead: bar = typical import, light bar = highest expected, red = above the target."""
    return _fill(
        "{% set s = '@S@' %}{% set hours = state_attr(s, 'hours') or [] %}{% set target = state_attr(s, 'target_kw') | float(10) %}"
        "{% if hours %}{% set ns = namespace(vmax=target * 1.25, g='') %}"
        "{% for h in hours %}{% if (h.get('high') or 0) * 1.1 > ns.vmax %}{% set ns.vmax = (h.get('high') or 0) * 1.1 %}{% endif %}{% endfor %}"
        "{% set W = 720 %}{% set H = 240 %}{% set L = 40 %}{% set R = 12 %}{% set T = 16 %}{% set B = 30 %}"
        "{% set pw = W - L - R %}{% set ph = H - T - B %}{% set bw = pw / 24 %}"
        + _fill(SVG_OPEN, H="240") + _axis() +
        "{% for h in hours %}{% set x = L + loop.index0 * bw %}{% set hi = h.get('high') or 0 %}{% set ty = h.get('typical') or 0 %}"
        "{% set hh = [hi / ns.vmax * ph, 0] | max %}{% set th = [ty / ns.vmax * ph, 0] | max %}"
        "{% set c = '@RED@' if hi > target else '@BLUE@' %}"
        "{% set ns.g = ns.g ~ \"<rect x='\" ~ (x + 1.5) ~ \"' y='\" ~ (T + ph - hh) ~ \"' width='\" ~ (bw - 3) ~ \"' height='\" ~ hh ~ \"' rx='2' fill='\" ~ c ~ \"' fill-opacity='0.35'/>"
        "<rect x='\" ~ (x + 1.5) ~ \"' y='\" ~ (T + ph - th) ~ \"' width='\" ~ (bw - 3) ~ \"' height='\" ~ th ~ \"' rx='2' fill='\" ~ c ~ \"'/>\" %}"
        "{% if (h.get('t')[11:13] | int) % 3 == 0 %}{% set ns.g = ns.g ~ \"<text x='\" ~ (x + bw / 2) ~ \"' y='\" ~ (H - 10) ~ \"' text-anchor='middle' fill='@GREY@'>\" ~ h.get('t')[11:13] ~ \"</text>\" %}{% endif %}"
        "{% endfor %}"
        + _limit_line("target", target_label) +
        "{% set ns.g = ns.g ~ '</svg>' %}" + SVG_IMAGE + "\n\n" + legend +
        "{% else %}" + none_text + "{% endif %}",
        S=ids["forecast_peak"], GREY=GREY, RED=RED, BLUE=BLUE,
    )


def profile(ids: dict[str, str], day_names: str, hour_label: str, legend: str, none_text: str) -> str:
    """Heat map of the usual week: rows = weekdays, columns = hours; two panels (typical, highest)."""
    return _fill(
        "{% set s = '@S@' %}{% set prof = state_attr(s, 'profile') or [] %}{% set target = state_attr('@P@', 'target_kw') | float(10) %}"
        "{% set names = '@N@'.split(',') %}"
        "{% if prof %}{% set ns = namespace(vmax=target, g='') %}"
        "{% for d in prof %}{% for v in d.get('high') %}{% if v is not none and v > ns.vmax %}{% set ns.vmax = v %}{% endif %}{% endfor %}{% endfor %}"
        "{% set W = 720 %}{% set L = 34 %}{% set R = 10 %}{% set cw = (W - L - R) / 24 %}{% set rh = 20 %}{% set H = 2 * (7 * rh + 40) %}"
        "{% set ns.g = \"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 720 \" ~ H ~ \"' font-family='Roboto,Arial,sans-serif' font-size='12'>\" %}"
        "{% for panel in range(2) %}{% set oy = panel * (7 * rh + 40) %}"
        "{% set ns.g = ns.g ~ \"<text x='\" ~ L ~ \"' y='\" ~ (oy + 14) ~ \"' fill='@GREY@' font-weight='700'>\" ~ ('@T1@' if panel == 0 else '@T2@') ~ \"</text>\" %}"
        "{% for d in prof %}{% set row = d.get('day') %}"
        "{% set ns.g = ns.g ~ \"<text x='\" ~ (L - 6) ~ \"' y='\" ~ (oy + 22 + row * rh + 14) ~ \"' text-anchor='end' fill='@GREY@'>\" ~ names[row] ~ \"</text>\" %}"
        "{% set vals = d.get('typical') if panel == 0 else d.get('high') %}"
        "{% for v in vals %}{% set x = L + loop.index0 * cw %}{% set y = oy + 22 + row * rh %}"
        "{% if v is none %}{% set ns.g = ns.g ~ \"<rect x='\" ~ x ~ \"' y='\" ~ y ~ \"' width='\" ~ (cw - 1) ~ \"' height='\" ~ (rh - 1) ~ \"' fill='@GREY@' fill-opacity='0.08'/>\" %}"
        "{% else %}{% set op = [0.12 + 0.88 * v / ns.vmax, 1] | min %}{% set c = '@RED@' if v > target else '@BLUE@' %}"
        "{% set ns.g = ns.g ~ \"<rect x='\" ~ x ~ \"' y='\" ~ y ~ \"' width='\" ~ (cw - 1) ~ \"' height='\" ~ (rh - 1) ~ \"' fill='\" ~ c ~ \"' fill-opacity='\" ~ op ~ \"'/>\" %}{% endif %}"
        "{% endfor %}{% endfor %}"
        "{% for hh in [0, 6, 12, 18] %}{% set ns.g = ns.g ~ \"<text x='\" ~ (L + hh * cw) ~ \"' y='\" ~ (oy + 22 + 7 * rh + 14) ~ \"' fill='@GREY@'>\" ~ hh ~ \"</text>\" %}{% endfor %}"
        "{% endfor %}"
        "{% set ns.g = ns.g ~ \"<text x='\" ~ (W - R) ~ \"' y='\" ~ (H - 4) ~ \"' text-anchor='end' fill='@GREY@'>@HL@</text></svg>\" %}"
        + SVG_IMAGE + "\n\n" + legend + " (max. {{ '%.1f' | format(ns.vmax) }} kW)"
        "{% else %}" + none_text + "{% endif %}",
        S=ids["forecast_now"], P=ids["status"], N=day_names, T1=hour_label.split("|")[0], T2=hour_label.split("|")[1],
        HL=hour_label.split("|")[2], GREY=GREY, RED=RED, BLUE=BLUE,
    )


def daily(ids: dict[str, str], limit_label: str, legend: str, none_text: str, days: int = 42) -> str:
    """Bars of the highest quarter hour per day for the last `days` days, red above the limit."""
    return _fill(
        "{% set peaks = state_attr('@S@', 'peaks_by_day') or {} %}{% set target = states('@LIM@') | float(10) %}"
        "{% if peaks %}{% set ns = namespace(vmax=target * 1.25, g='') %}"
        "{% for k, v in peaks.items() %}{% if v * 1.1 > ns.vmax %}{% set ns.vmax = v * 1.1 %}{% endif %}{% endfor %}"
        "{% set today = now().date() %}{% set W = 720 %}{% set H = 240 %}{% set L = 40 %}{% set R = 12 %}{% set T = 16 %}{% set B = 30 %}"
        "{% set pw = W - L - R %}{% set ph = H - T - B %}{% set n = @N@ %}{% set bw = pw / n %}"
        + _fill(SVG_OPEN, H="240") + _axis() +
        "{% for i in range(n) %}{% set day = today - timedelta(days=n - 1 - i) %}{% set v = peaks.get(day.strftime('%Y-%m-%d')) %}{% set x = L + i * bw %}"
        "{% if v is not none %}{% set hh = [v / ns.vmax * ph, 0] | max %}{% set c = '@RED@' if v > target else '@BLUE@' %}"
        "{% set ns.g = ns.g ~ \"<rect x='\" ~ (x + 1) ~ \"' y='\" ~ (T + ph - hh) ~ \"' width='\" ~ (bw - 2) ~ \"' height='\" ~ hh ~ \"' rx='2' fill='\" ~ c ~ \"'/>\" %}{% endif %}"
        "{% if day.weekday() == 0 %}{% set ns.g = ns.g ~ \"<text x='\" ~ (x + bw / 2) ~ \"' y='\" ~ (H - 10) ~ \"' text-anchor='middle' fill='@GREY@'>\" ~ day.strftime('%d.%m.') ~ \"</text>\" %}{% endif %}"
        "{% endfor %}"
        + _limit_line("target", limit_label) +
        "{% set ns.g = ns.g ~ '</svg>' %}" + SVG_IMAGE + "\n\n" + legend +
        "{% else %}" + none_text + "{% endif %}",
        S=ids["today_peak"], LIM=ids["limit"], N=str(days), GREY=GREY, RED=RED, BLUE=BLUE,
    )


def months(ids: dict[str, str], limit_label: str, legend: str, none_text: str) -> str:
    """Bars per month: peak (solid), peak without the guard (outline) and the limit."""
    return _fill(
        "{% set m = state_attr('@S@', 'months') or [] %}{% set target = states('@LIM@') | float(10) %}"
        "{% if m %}{% set ns = namespace(vmax=target * 1.25, g='') %}"
        "{% for r in m %}{% set a = [r.get('peak_kw') or 0, r.get('peak_without_kw') or 0] | max %}{% if a * 1.1 > ns.vmax %}{% set ns.vmax = a * 1.1 %}{% endif %}{% endfor %}"
        "{% set W = 720 %}{% set H = 240 %}{% set L = 40 %}{% set R = 12 %}{% set T = 16 %}{% set B = 30 %}"
        "{% set pw = W - L - R %}{% set ph = H - T - B %}{% set n = m | length %}{% set bw = pw / n %}"
        + _fill(SVG_OPEN, H="240") + _axis() +
        "{% for r in m %}{% set x = L + loop.index0 * bw %}{% set v = r.get('peak_kw') or 0 %}{% set u = r.get('peak_without_kw') or 0 %}"
        "{% set hh = v / ns.vmax * ph %}{% set uh = u / ns.vmax * ph %}{% set c = '@RED@' if v > target else '@BLUE@' %}"
        "{% if u > v + 0.05 %}{% set ns.g = ns.g ~ \"<rect x='\" ~ (x + 8) ~ \"' y='\" ~ (T + ph - uh) ~ \"' width='\" ~ (bw - 16) ~ \"' height='\" ~ uh ~ \"' rx='3' fill='none' stroke='@GREY@' stroke-width='2' stroke-dasharray='4 3'/>\" %}{% endif %}"
        "{% set ns.g = ns.g ~ \"<rect x='\" ~ (x + 8) ~ \"' y='\" ~ (T + ph - hh) ~ \"' width='\" ~ (bw - 16) ~ \"' height='\" ~ hh ~ \"' rx='3' fill='\" ~ c ~ \"'/>"
        "<text x='\" ~ (x + bw / 2) ~ \"' y='\" ~ (T + ph - hh - 4) ~ \"' text-anchor='middle' fill='@GREY@' font-weight='700'>\" ~ ('%.1f' | format(v)) ~ \"</text>"
        "<text x='\" ~ (x + bw / 2) ~ \"' y='\" ~ (H - 10) ~ \"' text-anchor='middle' fill='@GREY@'>\" ~ r.get('month')[5:7] ~ '/' ~ r.get('month')[2:4] ~ \"</text>\" %}"
        "{% endfor %}"
        + _limit_line("target", limit_label) +
        "{% set ns.g = ns.g ~ '</svg>' %}" + SVG_IMAGE + "\n\n" + legend +
        "{% else %}" + none_text + "{% endif %}",
        S=ids["month_peak"], LIM=ids["limit"], GREY=GREY, RED=RED, BLUE=BLUE,
    )
