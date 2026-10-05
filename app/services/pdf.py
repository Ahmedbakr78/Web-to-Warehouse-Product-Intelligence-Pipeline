"""PDF report rendering with WeasyPrint.

Reports are described declaratively (see `app/services/report.py`) and rendered
through WeasyPrint's HTML backend. HTML-in-PDF rather than a drawing API, because a
report is mostly text and tables and HTML gives accessible markup, selectable text and
a real stylesheet for a fraction of the effort of manual layout.

WeasyPrint needs system libraries (Pango, cairo, GDK-Pixbuf). They are present in the
API container and on a normal desktop, but on a minimal Python image the import fails.
That is handled as a normal condition: `available()` reports it, the endpoints return
a clear 501, and CSV/JSON export keeps working.
"""

from __future__ import annotations

import datetime as dt
import html
import math
from collections.abc import Sequence
from typing import Any

from app.core.logging import get_logger

log = get_logger(__name__)

#: A4 at 96 dpi, which is what WeasyPrint expects.
PAGE = {"size": "A4", "margin": "16mm 14mm"}
#: Placeholder replaced per render with the actual generation time.
STAMP_PLACEHOLDER = "__GENERATED_AT__"

#: Brand palette, matching the dashboard's CSS custom properties.
INK = "#0f172a"
MUTED = "#475569"
LINE = "#e2e8f0"
BRAND = "#4f46e5"
SUCCESS = "#059669"
DANGER = "#dc2626"
WARNING = "#b45309"


def available() -> bool:
    """True when WeasyPrint can be imported and can actually write a PDF."""
    try:
        import weasyprint  # noqa: F401
    except Exception:  # noqa: BLE001 - missing system libraries are an expected outcome
        return False
    return True


def unavailable_reason() -> str:
    try:
        import weasyprint  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        return (
            f"WeasyPrint is not usable here ({type(exc).__name__}: {exc}). "
            "It needs the Pango, cairo and GDK-Pixbuf system libraries; "
            "install them or use the CSV and JSON exports instead."
        )
    return ""


def _escape(value: Any) -> str:
    if value is None:
        return "&mdash;"
    if isinstance(value, float):
        if not math.isfinite(value):
            return "&mdash;"
        text = f"{value:,.2f}".rstrip("0").rstrip(".")
        return html.escape(text)
    if isinstance(value, dt.datetime):
        return html.escape(value.strftime("%Y-%m-%d %H:%M"))
    if isinstance(value, dt.date):
        return html.escape(value.isoformat())
    return html.escape(str(value))


# --------------------------------------------------------------------------------------
# CSS
# --------------------------------------------------------------------------------------
STYLESHEET = f"""
@page {{
  size: {PAGE["size"]};
  margin: {PAGE["margin"]};

  @bottom-center {{
    content: "Page " counter(page) " of " counter(pages);
    font-size: 8pt;
    color: {MUTED};
  }}
  @bottom-right {{
    /* WeasyPrint does not implement attr() inside page margin boxes, so the
       generation stamp is substituted into this template at render time. */
    content: "__STAMP__";
    font-size: 8pt;
    color: {MUTED};
  }}
}}

* {{ box-sizing: border-box; }}

body {{
  font-family: "Inter", "DejaVu Sans", sans-serif;
  font-size: 9pt;
  color: {INK};
  line-height: 1.45;
  margin: 0;
}}

h1 {{ font-size: 19pt; margin: 0 0 2mm; letter-spacing: -0.3pt; }}
h2 {{
  font-size: 11pt; margin: 7mm 0 2mm; padding-bottom: 1.5mm;
  border-bottom: 1px solid {LINE};
}}
h3 {{ font-size: 9.5pt; margin: 4mm 0 1.5mm; color: {MUTED}; }}

p {{ margin: 0 0 2.5mm; }}

.subtitle {{ color: {MUTED}; font-size: 9.5pt; margin: 0 0 5mm; }}

.header {{
  display: flex; justify-content: space-between; align-items: flex-start;
  border-bottom: 2px solid {BRAND}; padding-bottom: 3mm; margin-bottom: 5mm;
}}
.brand {{ display: flex; align-items: center; gap: 3mm; }}
.brand-mark {{
  width: 7mm; height: 7mm; border-radius: 2mm; background: {BRAND};
}}
.brand-name {{ font-weight: 700; font-size: 11pt; }}
.brand-sub {{ color: {MUTED}; font-size: 8pt; }}
.meta {{ text-align: right; font-size: 8pt; color: {MUTED}; }}

.tiles {{ display: flex; flex-wrap: wrap; gap: 3mm; margin-bottom: 4mm; }}
.tile {{
  flex: 1 1 30mm; border: 1px solid {LINE}; border-radius: 2mm; padding: 2.5mm 3mm;
}}
.tile-label {{ font-size: 7.5pt; color: {MUTED}; text-transform: uppercase; letter-spacing: 0.4pt; }}
.tile-value {{ font-size: 14pt; font-weight: 700; margin-top: 0.8mm; }}
.tile-hint {{ font-size: 7.5pt; color: {MUTED}; margin-top: 0.5mm; }}

table {{ width: 100%; border-collapse: collapse; margin-bottom: 3mm; }}
thead {{ display: table-header-group; }}
th {{
  text-align: left; font-size: 7.5pt; text-transform: uppercase; letter-spacing: 0.4pt;
  color: {MUTED}; border-bottom: 1px solid {INK}; padding: 1.6mm 2mm;
  background: #f8fafc;
}}
td {{ padding: 1.6mm 2mm; border-bottom: 1px solid {LINE}; }}
tbody tr:nth-child(even) {{ background: #fbfcfe; }}
.num {{ text-align: right; font-variant-numeric: tabular-nums; }}

.badge {{
  display: inline-block; padding: 0.4mm 1.6mm; border-radius: 1mm;
  font-size: 7.5pt; font-weight: 600;
}}
.badge-success {{ background: #d1fae5; color: {SUCCESS}; }}
.badge-danger {{ background: #fee2e2; color: {DANGER}; }}
.badge-warning {{ background: #fef3c7; color: {WARNING}; }}
.badge-neutral {{ background: #e2e8f0; color: {MUTED}; }}

/* Inline bar chart: no image dependency, so it renders identically everywhere. */
.bars {{ margin: 2mm 0 4mm; }}
.bar-row {{ display: flex; align-items: center; gap: 2mm; margin-bottom: 1.4mm; }}
.bar-label {{ width: 42mm; font-size: 8pt; overflow-wrap: anywhere; }}
.bar-track {{ flex: 1; background: #f1f5f9; border-radius: 1mm; height: 4mm; }}
.bar-fill {{ height: 4mm; border-radius: 1mm; background: {BRAND}; }}
.bar-value {{ width: 16mm; text-align: right; font-size: 8pt; font-variant-numeric: tabular-nums; }}

.callout {{
  border-left: 2.5mm solid {BRAND}; background: #eef2ff;
  padding: 2.5mm 3mm; margin-bottom: 3mm;
}}
.callout-title {{ font-weight: 700; margin-bottom: 1mm; }}

.note {{ font-size: 7.5pt; color: {MUTED}; font-style: italic; margin-top: -1.5mm; }}

footer {{
  margin-top: 8mm; padding-top: 2mm; border-top: 1px solid {LINE};
  font-size: 7.5pt; color: {MUTED};
}}
"""


# --------------------------------------------------------------------------------------
# Blocks
# --------------------------------------------------------------------------------------
def _tile(label: str, value: Any, hint: str | None = None, tone: str | None = None) -> str:
    colour = {"success": SUCCESS, "danger": DANGER, "warning": WARNING}.get(tone or "", INK)
    hint_html = f'<div class="tile-hint">{html.escape(hint)}</div>' if hint else ""
    return (
        f'<div class="tile"><div class="tile-label">{html.escape(label)}</div>'
        f'<div class="tile-value" style="color:{colour}">{_escape(value)}</div>{hint_html}</div>'
    )


def _table(columns: Sequence[dict[str, Any]], rows: Sequence[dict[str, Any]], max_rows: int = 200) -> str:
    if not rows:
        return '<p class="note">No rows matched.</p>'
    shown = rows[:max_rows]

    def cell(row: dict[str, Any], column: dict[str, Any]) -> str:
        value = row.get(column["key"])
        badge = column.get("badge")
        if badge:
            tone = {
                "success": "badge-success",
                "danger": "badge-danger",
                "warning": "badge-warning",
            }.get(str(badge(value)).lower(), "badge-neutral")
            return f'<span class="badge {tone}">{_escape(badge(value))}</span>'
        align = ' class="num"' if column.get("align") == "right" else ""
        return f"<td{align}>{_escape(value)}</td>"

    def header_cell(column: dict[str, Any]) -> str:
        """One `<th>`, right-aligned for numeric columns."""
        label = html.escape(str(column["label"]))
        style = ' style="text-align:right"' if column.get("align") == "right" else ""
        return f"<th{style}>{label}</th>"

    head = "".join(header_cell(column) for column in columns)
    body = "".join("<tr>" + "".join(cell(row, column) for column in columns) + "</tr>" for row in shown)
    table = f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
    if len(rows) > max_rows:
        table += (
            f'<p class="note">Showing the first {max_rows} of {len(rows):,} rows. '
            "Use a CSV export for the full set.</p>"
        )
    return table


def _bars(items: Sequence[dict[str, Any]], *, palette: Sequence[str] = (BRAND,)) -> str:
    """A horizontal bar chart drawn in HTML, so no image library is needed."""
    entries = [item for item in items if item.get("value") is not None]
    if not entries:
        return '<p class="note">Nothing to plot.</p>'
    peak = max(abs(float(item["value"])) for item in entries) or 1.0

    rows = []
    for index, item in enumerate(entries):
        share = abs(float(item["value"])) / peak * 100
        colour = palette[index % len(palette)]
        rows.append(
            f'<div class="bar-row"><div class="bar-label">{_escape(item["label"])}</div>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{share:.2f}%;'
            f'background:{colour}"></div></div>'
            f'<div class="bar-value">{_escape(item["value"])}</div></div>'
        )
    return f'<div class="bars">{"".join(rows)}</div>'


def _callout(title: str, body: str) -> str:
    return (
        f'<div class="callout"><div class="callout-title">{html.escape(title)}</div><div>{body}</div></div>'
    )


# --------------------------------------------------------------------------------------
# Document assembly
# --------------------------------------------------------------------------------------
def stylesheet(stamp: str | None = None) -> str:
    """The report stylesheet, with the page-footer stamp substituted in."""
    generated = stamp or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return STYLESHEET.replace("__STAMP__", generated)


def render_blocks(title: str, subtitle: str, blocks: Sequence[dict[str, Any]], *, footer: str = "") -> str:
    """Assemble a full HTML document from declarative blocks."""
    generated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    palette = (BRAND, "#0891b2", SUCCESS, WARNING, "#7c3aed", DANGER)

    parts: list[str] = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<title>{html.escape(title)}</title>",
        f"<style>{stylesheet(generated)}</style></head><body>",
        '<div class="header"><div class="brand"><div class="brand-mark"></div><div>',
        '<div class="brand-name">Product Intelligence</div>',
        '<div class="brand-sub">Web-to-Warehouse Pipeline</div></div></div>',
        f'<div class="meta">{html.escape(generated)}</div></div>',
        f"<h1>{html.escape(title)}</h1>",
        f'<p class="subtitle">{html.escape(subtitle)}</p>' if subtitle else "",
    ]

    for block in blocks:
        kind = block.get("type")
        if kind == "tiles":
            tiles = "".join(
                _tile(
                    str(tile.get("label", "")),
                    tile.get("value"),
                    tile.get("hint"),
                    tile.get("tone"),
                )
                for tile in block.get("tiles", [])
            )
            parts.append(f'<div class="tiles">{tiles}</div>')
        elif kind == "heading":
            parts.append(f"<h2>{html.escape(str(block.get('title', '')))}</h2>")
        elif kind == "text":
            parts.append(f"<p>{html.escape(str(block.get('body', '')))}</p>")
        elif kind == "callout":
            parts.append(_callout(str(block.get("title", "")), str(block.get("body", ""))))
        elif kind == "table":
            parts.append(_table(block.get("columns", []), block.get("rows", [])))
        elif kind == "bars":
            parts.append(_bars(block.get("items", []), palette=palette))
        elif kind == "forecast":
            points = block.get("points", [])
            if points:
                values = [float(point["value"]) for point in points]
                parts.append(
                    _bars(
                        [
                            {"label": str(point["date"])[5:], "value": round(value, 2)}
                            for point, value in zip(points, values, strict=False)
                        ]
                    )
                )
            else:
                parts.append('<p class="note">No forecast available for this product.</p>')

    parts.append(f"<footer>{html.escape(footer)}</footer>" if footer else "")
    parts.append("</body></html>")
    return "".join(part for part in parts if part)


def to_pdf(document: str, *, base_url: str | None = None) -> bytes:
    """Render an HTML document to PDF bytes."""
    if not available():
        raise RuntimeError(unavailable_reason() or "WeasyPrint is unavailable")
    import io

    import weasyprint

    buffer = io.BytesIO()
    weasyprint.HTML(string=document, base_url=base_url).write_pdf(buffer)
    return buffer.getvalue()


def html_to_pdf(document: str, *, base_url: str | None = None) -> bytes:
    return to_pdf(document, base_url=base_url)


__all__ = [
    "available",
    "html_to_pdf",
    "render_blocks",
    "stylesheet",
    "to_pdf",
    "unavailable_reason",
]
