"""Charts full screen (pure Python, no Home Assistant imports).

The Home Assistant app does not let a dashboard be zoomed with two fingers. Every chart of the generated dashboard is therefore a
link to a page of its own (vollbild_view.py) that shows the same chart over the whole width and may be zoomed. The page renders
the card's own template again, so it always shows the current state. The link carries a random key of this installation: the page
needs no login (the app opens it in the browser), but nobody can guess it, and it only ever shows the charts of this dashboard.
"""

from __future__ import annotations

import hashlib
import html
import re
from typing import Any

# the chart image of a markdown card: ![](data:image/svg+xml;utf8,{{ ... | urlencode }})
IMAGE = re.compile(r"!\[\]\(data:image/svg\+xml;utf8,\{\{.*?\}\}\)", re.S)
RENDERED = re.compile(r"data:image/svg\+xml;utf8,([^)\s\"'<>]+)")

TEXT = {
    "de": ("Zum Vergrößern mit zwei Fingern ziehen oder das Handy quer halten. Neu laden zeigt den aktuellen Stand.",
           "Diese Grafik ist gerade leer (noch keine Daten).", "← Zurück"),
    "en": ("Pinch with two fingers to zoom, or turn the phone sideways. Reload for the current state.",
           "This chart is empty right now (no data yet).", "← Back"),
}


def chart_id(content: str) -> str:
    """A short, stable name of a chart card (the same card gets the same name every time the dashboard is built)."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def link_charts(node: Any, base: str, key: str) -> dict[str, str]:
    """Makes every chart of the dashboard config `node` (changed in place) a link to its full-screen page `base/key/id` and
    returns {id: card template} for the page to render. `target="_self"`: the app opens the page in itself (a link without a
    target is taken over by the dashboard's own navigation, `_blank` leaves the app for the browser)."""
    found: dict[str, str] = {}

    def walk(n: Any) -> None:
        if isinstance(n, list):
            for x in n:
                walk(x)
        elif isinstance(n, dict):
            content = n.get("content")
            if n.get("type") == "markdown" and isinstance(content, str) and IMAGE.search(content):
                cid = chart_id(content)
                found[cid] = content
                href = f"{base}/{key}/{cid}"
                n["content"] = IMAGE.sub(lambda m: f'<a href="{href}" target="_self">{m.group(0)}</a>', content)
            for x in n.values():
                if isinstance(x, (list, dict)):
                    walk(x)

    walk(node)
    return found


def extract_image(rendered: str) -> str | None:
    """The url-encoded SVG of the first chart in a rendered card (None: the card shows no chart right now)."""
    m = RENDERED.search(rendered or "")
    return m.group(1) if m else None


def back_path(referer: str | None, host: str | None) -> str:
    """Where "back" leads: the dashboard the chart was opened from (same server only), else the start page."""
    from urllib.parse import urlsplit

    try:
        u = urlsplit(referer or "")
    except ValueError:
        return "/"
    if not u.path.startswith("/") or u.path.startswith("//") or (u.netloc and u.netloc != (host or "")):
        return "/"
    return u.path + (f"?{u.query}" if u.query else "")


def page(title: str, image: str | None, language: str | None, back: str = "/") -> str:
    """The full-screen page: the chart as an image (an SVG image cannot run scripts), zoom allowed, light and dark."""
    hint, empty, back_text = TEXT["de" if str(language or "").lower().startswith("de") else "en"]
    body = (f'<img src="data:image/svg+xml;utf8,{html.escape(image, quote=True)}" alt="{html.escape(title)}">' if image
            else f"<p>{html.escape(empty)}</p>")
    return ("<!doctype html><html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1, minimum-scale=1, maximum-scale=10, user-scalable=yes'>"
            "<meta name='robots' content='noindex'>"
            f"<title>{html.escape(title)}</title><style>"
            ":root{color-scheme:light dark}body{margin:0;padding:12px;background:#111827;color:#cbd5e1;font:14px sans-serif}"
            "@media (prefers-color-scheme: light){body{background:#f8fafc;color:#334155}}"
            "img{display:block;width:100%;height:auto}p{margin:12px 0 0;opacity:.8}"
            "a{display:inline-block;margin:0 0 12px;padding:8px 14px;border-radius:8px;background:#2563eb;color:#fff;text-decoration:none}"
            f"</style></head><body><a href=\"{html.escape(back, quote=True)}\">{html.escape(back_text)}</a>{body}<p>{html.escape(hint)}</p></body></html>")
