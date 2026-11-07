"""One-off: the shipped dashboard cleaned up like the one of the author (user 07.11.2026: fewer cards, graphics instead of text,
settings stay). Kept for the record."""
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "custom_components" / "viertelstunden_waechter" / "dashboard.py"
s = p.read_text(encoding="utf-8")


def rep(a, b):
    global s
    assert s.count(a) == 1, a[:90]
    s = s.replace(a, b)


# main view: no explanation text, no configuration table, only the important tiles
rep('''                {"type": "heading", "heading": x["view_main"], "icon": "mdi:shield-half-full"},
                {"type": "markdown", "content": x["intro"]},
''', '''                {"type": "heading", "heading": x["view_main"], "icon": "mdi:shield-half-full"},
''')
rep('''                {"type": "markdown", "title": x["devices"], "content": _config_markdown(ids, x)},
''', '')
rep('''                _tile(ids["status"], x["status"]), _tile(ids["forecast"], x["prognosis"]), _tile(ids["allowed"], x["allowed"]),
                _tile(ids["quarter_energy"], x["so_far"]), _tile(ids["last_quarter"], x["last"]),
                _tile(ids["today_peak"], x["peak_today"]), _tile(ids["month_peak"], x["peak_month"]),
                _tile(ids["interventions_today"], x["iv_today"]),
                {"type": "markdown", "content": _today_markdown(ids, x)},
''', '''                _tile(ids["status"], x["status"]), _tile(ids["forecast"], x["prognosis"]),
                _tile(ids["today_peak"], x["peak_today"]), _tile(ids["month_peak"], x["peak_month"]),
                _tile(ids["interventions_today"], x["iv_today"]),
''')
rep('''                _tile(ids["cost_month"], x["cost_month"]), _tile(ids["cost_without"], x["cost_without"]),
                _tile(ids["savings_month"], x["saving_month"]), _tile(ids["savings_year"], x["saving_year"]),
                _tile(ids["saved_now"], x["saved_now"]),
                {"type": "markdown", "content": x["estimate"]},
''', '''                _tile(ids["cost_month"], x["cost_month"]),
                _tile(ids["savings_month"], x["saving_month"]), _tile(ids["savings_year"], x["saving_year"]),
''')
# today view: the explanation of the day only while the AI explainer is on
rep('''                {"type": "heading", "heading": x["ai_title"], "icon": "mdi:robot-outline"},
                {"type": "markdown", "content": _explanation_markdown(ids, x)},
            ]},
        ],
    }
    stats = {''', '''                {"type": "conditional", "conditions": [{"condition": "state", "entity": ids["ai_explainer"], "state": "on"}],
                 "card": {"type": "markdown", "title": x["ai_title"], "content": _explanation_markdown(ids, x)}},
            ]},
        ],
    }
    stats = {''')
# statistics: graphics, one line for the next risk
rep('''                _tile(ids["forecast_now"], x["typical_now"]), _tile(ids["forecast_peak"], x["expected_peak"]),
                {"type": "markdown", "content": _next_risk_markdown(ids, x)},
                {"type": "markdown", "content": _forecast_markdown(ids, x)},
''', '''                {"type": "markdown", "content": _next_risk_markdown(ids, x)},
''')
rep('''                {"type": "heading", "heading": x["peaks"], "icon": "mdi:calendar-month"},
                {"type": "markdown", "content": _peaks_markdown(ids, x)},
                {"type": "heading", "heading": x["daily"], "icon": "mdi:chart-bar"},
                {"type": "markdown", "content": charts.daily(ids, x["limit_label"], x["legend_daily"], x["enough_data"])},
                {"type": "statistics-graph", "title": x["chart_peaks"], "entities": [ids["last_quarter"]],
                 "stat_types": ["max"], "period": "hour", "days_to_show": 3, "chart_type": "bar"},
''', '''                {"type": "heading", "heading": x["daily"], "icon": "mdi:chart-bar"},
                {"type": "markdown", "content": charts.daily(ids, x["limit_label"], x["legend_daily"], x["enough_data"])},
''')
rep('''                {"type": "markdown", "content": _months_markdown(ids, x)},
                {"type": "heading", "heading": x["interventions"], "icon": "mdi:counter"},
                {"type": "markdown", "content": _interventions_markdown(ids, x)},
                {"type": "heading", "heading": x["ai_title"], "icon": "mdi:robot-outline"},
                {"type": "markdown", "content": _explanation_markdown(ids, x)},
''', '')
# charge plan: the plan only (readiness and the forecast line are in the planner's own dashboard)
rep('''            {"type": "markdown", "content": _plan_markdown(ids, x)},
            {"type": "markdown", "content": _car_plan_markdown(ids, x)},
        ]}''', '''            {"type": "markdown", "content": _plan_markdown(ids, x)},
        ]}''')
rep('''        cards.append(_tile(p["plan"], f"{x['plan_status']} · {name}" if name and len(planners) > 1 else x["plan_status"]))
        if p.get("ready"):
            cards.append(_tile(p["ready"], f"{x['readiness']} · {name}" if name and len(planners) > 1 else x["readiness"]))
        cards.append({"type": "markdown", "content": _planner_markdown(p["plan"], x)})
    cards.append({"type": "markdown", "content": _car_plan_markdown(ids, x) + "\\n\\n*" + x["planner_note"] + "*"})
    return {"type": "grid", "cards": cards}''', '''        cards.append(_tile(p["plan"], f"{x['plan_status']} · {name}" if name and len(planners) > 1 else x["plan_status"]))
        cards.append({"type": "markdown", "content": _planner_markdown(p["plan"], x)})
    return {"type": "grid", "cards": cards}''')
p.write_text(s, encoding="utf-8")
print("ok")
