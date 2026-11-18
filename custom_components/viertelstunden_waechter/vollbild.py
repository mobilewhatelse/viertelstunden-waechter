"""Charts full width (pure Python, no Home Assistant imports).

The Home Assistant app does not let a dashboard be zoomed with two fingers. A tap on a chart of the generated dashboard opens a
subview of the dashboard with that card (chart and caption) over the whole width; held sideways the chart is large. The link is
relative, so the dashboard switches without loading the app again (a page outside the dashboard made the app load again on the
way there and back, 18.11.2026); the subview has the usual back arrow.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

# the chart image of a markdown card: ![](data:image/svg+xml;utf8,{{ ... | urlencode }})
IMAGE = re.compile(r"!\[\]\(data:image/svg\+xml;utf8,\{\{.*?\}\}\)", re.S)
CHART = {"de": "Grafik", "en": "Chart"}


def chart_id(content: str) -> str:
    """A short, stable name of a chart card (the same card gets the same name every time the dashboard is built)."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def link_charts(node: Any, language: str | None = None) -> list[str]:
    """Every chart of the dashboard config `node` (changed in place) becomes a link to a subview `grafik-<id>` that shows the
    whole card over the full width. The subviews are added to `node["views"]`. Returns the ids."""
    found: list[str] = []
    subviews: list[dict[str, Any]] = []
    fallback = CHART["de" if str(language or "").lower().startswith("de") else "en"]

    def chart(card: dict[str, Any], title: str | None) -> None:
        content = card["content"]
        cid = chart_id(content)
        path = f"grafik-{cid}"
        card["content"] = IMAGE.sub(lambda m: f'<a href="{path}">{m.group(0)}</a>', content)
        if cid in found:
            return
        found.append(cid)
        subviews.append({"title": title or fallback, "path": path, "subview": True, "type": "panel",
                         "cards": [{"type": "markdown", "content": content}]})

    def walk(n: Any, title: str | None) -> None:
        if isinstance(n, list):
            for x in n:
                if isinstance(x, dict) and x.get("type") == "heading" and x.get("heading"):
                    title = str(x["heading"])
                walk(x, title)
        elif isinstance(n, dict):
            content = n.get("content")
            if n.get("type") == "markdown" and isinstance(content, str) and IMAGE.search(content):
                chart(n, title)
            for x in n.values():
                if isinstance(x, (list, dict)):
                    walk(x, title)

    walk(node, None)
    if isinstance(node, dict) and isinstance(node.get("views"), list):
        node["views"].extend(subviews)
    return found
