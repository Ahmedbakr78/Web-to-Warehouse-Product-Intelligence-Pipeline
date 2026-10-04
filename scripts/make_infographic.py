#!/usr/bin/env python3
"""Generate the DEPI project roadmap infographic (16:9, presentation-first).

Outputs:
  docs/assets/infographic.svg      vector master (2560x1440), drops into PowerPoint / Keynote
  docs/assets/infographic.html     full-bleed 16:9 preview wrapper
  docs/assets/infographic.png      raster export, drawn only if `cairosvg` is installed

The slide summarises the shipped system only - facts are read from the cited CLI commands,
never invented. Run it with:  make infographic
"""

from __future__ import annotations

import html
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "assets"

W, H = 2560, 1440
SVG_NS = "http://www.w3.org/2000/svg"

# ---- palette (delivery brief: deep blue primary, purple secondary, cyan accent,
# ---- orange highlight, green success, light background)
PRIMARY = "#1B3A8A"
PRIMARY_LIGHT = "#2E4FA8"
SECONDARY = "#7C3AED"
ACCENT = "#06B6D4"
HIGHLIGHT = "#F59E0B"
SUCCESS = "#10B981"
BG = "#F7F9FC"
CARD = "#FFFFFF"
INK = "#0F172A"
MUTED = "#64748B"
LINE = "#E2E8F0"

ROADMAP = [
    (
        "Overview",
        "Web-to-Warehouse product intelligence",
        "box",
        ["permitted web sources", "retailer catalog"],
    ),
    ("Problem", "Manual collection is slow and inconsistent", "alert", ["stale spreadsheets", "no history"]),
    ("Solution", "Compliance-first ETL pipeline", "gauge", ["robots.txt aware", "deduplicated"]),
    ("Architecture", "Airflow orchestrates 9 stages", "flow", ["ingest, clean, load", "detect, reconcile"]),
    ("Warehouse", "23 tables, 20 analytical views", "db", ["PostgreSQL twin", "MySQL twin"]),
    ("Data Quality", "12 rules across 6 dimensions", "shield", ["score persisted per run", "98.26 measured"]),
    ("Operations", "104 REST operations, 15 routers", "api", ["JWT + API keys", "role-scoped"]),
    ("Dashboard", "17 screens, light and dark", "screen", ["command palette", "installable PWA"]),
    ("Deployment", "6-service Compose stack", "cloud", ["Makefile targets", "GitHub Actions CI"]),
    ("Future", "SCD-2, webhooks, Grafana", "rocket", ["prioritised in docs/20", "open roadmap"]),
]

TECH_BADGES = [
    "Python 3.12",
    "FastAPI",
    "Airflow 2.10",
    "SQLAlchemy",
    "BeautifulSoup",
    "Scrapy",
    "React 19",
    "TypeScript",
    "Tailwind",
    "Recharts",
    "PostgreSQL 16",
    "MySQL 8.4",
    "JWT + Argon2id",
    "Docker Compose",
    "GitHub Actions",
    "pytest",
]

TIMELINE = ["Plan", "Design", "Build", "Test", "Deploy", "Maintain"]

OUTCOMES = [
    "Working pipeline",
    "23-table warehouse",
    "12-rule DQ gate",
    "REST API 104 ops",
    "React dashboard",
    "Airflow DAG 13 tasks",
    "CLI + Makefile",
    "CI green",
    "20 documents",
    "Private repo released",
]

ICON_PATHS = {
    "box": "M4 8l8-4 8 4-8 4-8-4zm0 0v8l8 4 8-4V8",
    "alert": "M12 4l9 16H3l9-16zm0 6v4m0 3v.5",
    "gauge": "M4 16a8 8 0 1116 0M12 16l4-5",
    "flow": "M5 6h6M5 12h9M5 18h6M15 6a3 3 0 110 6M17 12a3 3 0 110 6",
    "db": "M5 7c0-1.7 3.1-3 7-3s7 1.3 7 3-3.1 3-7 3-7-1.3-7-3zm0 0v10c0 1.7 3.1 3 7 3s7-1.3 7-3V7M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3",
    "shield": "M5 5h14v7c0 4.4-3 7.4-7 8-4-.6-7-3.6-7-8V5zm7 3v5m0 3v-1",
    "api": "M8 5l-5 7 5 7m8-14l5 7-5 7M13 6l-2 12",
    "screen": "M4 6h16v10H4V6zm5 14h6m-3-4v4",
    "cloud": "M7 17a4 4 0 010-8 5.5 5.5 0 0110.6 1.5A3.6 3.6 0 0117 17H7z",
    "rocket": "M12 4c3 1.5 5 4.5 5 8l-3 3h-4l-3-3c0-3.5 2-6.5 5-8zm0 5v3M6 17l-2 3 4-1m10-2l2 4-4-1M12 21v-3",
}


def esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def esctick(text: str) -> str:
    return esc(text)


def icon_icon(name: str, cx: float, cy: float, stroke: str, scale: float = 1.0, sw: float = 1.6) -> str:
    path = ICON_PATHS[name]
    s = scale * 1.05
    return (
        f'<g transform="translate({cx:.0f},{cy:.0f}) scale({s:.2f})" transform-origin="0 0" '
        f'stroke="{stroke}" stroke-width="{sw}" fill="none" stroke-linecap="round" '
        f'stroke-linejoin="round"><path transform="translate(-14,-14)" d="{path}"/></g>'
    )


def rounded(x: float, y: float, w: float, h: float, r: float, fill: str, stroke: str | None = None) -> str:
    stroke_attr = f' stroke="{stroke}" stroke-width="1.5"' if stroke else ""
    return f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" rx="{r:.0f}" ry="{r:.0f}" fill="{fill}"{stroke_attr}/>'


def text(
    x: float,
    y: float,
    content: str,
    size: int,
    weight: int = 500,
    fill: str = INK,
    anchor: str = "start",
    spacing: str = "0",
) -> str:
    return (
        f'<text x="{x:.0f}" y="{y:.0f}" font-family="Inter,Segoe UI,Arial,sans-serif" '
        f'font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}" '
        f'letter-spacing="{spacing}">{esc(content)}</text>'
    )


def build_svg() -> str:
    parts: list[str] = [
        f'<svg xmlns="{SVG_NS}" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" '
        f'aria-label="Web-to-Warehouse Product Intelligence Pipeline project infographic">',
        "<defs>",
        f'<linearGradient id="hdr" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0%" stop-color="{PRIMARY}"/><stop offset="55%" stop-color="{PRIMARY_LIGHT}"/>'
        f'<stop offset="100%" stop-color="{SECONDARY}"/></linearGradient>',
        f'<linearGradient id="band" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0%" stop-color="{PRIMARY}"/><stop offset="100%" stop-color="{SECONDARY}"/></linearGradient>',
        '<filter id="soft" x="-8%" y="-8%" width="116%" height="116%">'
        '<feDropShadow dx="0" dy="6" stdDeviation="10" flood-color="#0F172A" flood-opacity="0.08"/></filter>',
        "</defs>",
        f'<rect width="{W}" height="{H}" fill="{BG}"/>',
    ]

    # ---------------------------------------------------------------- header (about 8% height)
    hdr_h = 116
    parts.append(f'<rect x="0" y="0" width="{W}" height="{hdr_h}" rx="0" fill="url(#hdr)"/>')
    # DEPI wordmark block
    parts.append(rounded(70, 27, 62, 62, 14, CARD))
    parts.append(text(101, 58, "DE", 21, 700, PRIMARY, anchor="middle"))
    parts.append(text(101, 82, "PI", 21, 700, SECONDARY, anchor="middle"))
    parts.append(text(158, 53, "DEPI  |  Digital Egypt Pioneers Initiative", 26, 600, "#FFFFFF"))
    parts.append(text(158, 86, "Track: Data Engineering", 20, 400, "#D6DEF5"))
    # title + subtitle on the right
    parts.append(
        text(W - 70, 52, "Web-to-Warehouse Product Intelligence Pipeline", 30, 700, "#FFFFFF", anchor="end")
    )
    parts.append(
        text(
            W - 70,
            86,
            "Compliance-first ETL  |  Kimball warehouse  |  Data-quality gate  |  REST API  |  React dashboard",
            19,
            400,
            "#D6DEF5",
            anchor="end",
        )
    )

    # ---------------------------------------------------------------- key-number strip
    strip_y = hdr_h + 30
    numbers = [
        ("5", "ingestion sources", ACCENT),
        ("23/20", "tables / views", PRIMARY),
        ("12x6", "DQ rules x dimensions", SUCCESS),
        ("104", "REST operations", SECONDARY),
        ("98.26", "measured DQ score", HIGHLIGHT),
        ("38.2ms", "p95 API latency", ACCENT),
    ]
    cell_w = 336
    strip_w = cell_w * len(numbers)
    strip_x = (W - strip_w) // 2
    for index, (value, label, colour) in enumerate(numbers):
        x = strip_x + index * cell_w
        parts.append(rounded(x + 8, strip_y, cell_w - 16, 118, 18, CARD, LINE))
        parts.append(f'<filter id="s{index}" filter="url(#soft)"/>')
        parts.append(rounded(x + 8, strip_y + 108, cell_w - 16, 10, 5, colour))
        parts.append(text(x + cell_w / 2, strip_y + 56, value, 40, 700, colour, anchor="middle"))
        parts.append(text(x + cell_w / 2, strip_y + 90, label, 18, 500, MUTED, anchor="middle"))

    # ---------------------------------------------------------------- roadmap (left to right)
    road_y = strip_y + 196
    road_h = 560
    cols = 5
    rows = 2
    card_w = 424
    gap_x = 48
    total_w_of_road = cols * card_w + (cols - 1) * gap_x
    road_x = (W - total_w_of_road) // 2

    # thin connectors along a clean grid
    for row_index in range(rows):
        y = road_y + row_index * (road_h / 2) + 96
        for c in range(cols - 1):
            x1 = road_x + (c + 1) * card_w + c * gap_x
            x2 = x1 + gap_x - 18
            parts.append(
                f'<path d="M{x1:.0f} {y:.0f} H{x2:.0f}" stroke="{LINE}" stroke-width="3" fill="none"/>'
            )
            parts.append(f'<path d="M{x2:.0f} {y:.0f} l-12 -7 v14 z" fill="{LINE}"/>')

    for index, (title, subtitle, icon, keywords) in enumerate(ROADMAP):
        row_index, col_index = divmod(index, cols)
        x = road_x + col_index * (card_w + gap_x)
        y = road_y + row_index * (road_h / 2)
        step = index + 1
        parts.append(rounded(x, y, card_w, road_h / 2 - 36, 22, CARD, LINE))
        parts.append(
            f'<path d="M{x:.0f} {y:.0f} h{card_w:.0f} a22 22 0 0 1 22 22 v36 h-{card_w + 44:.0f} v-36 a22 22 0 0 1 22 -22 z" '
            f'fill="url(#band)" opacity="0.97"/>'
        )
        parts.append(
            text(x + card_w / 2, y + 44, f"{step:02d}  {title}", 24, 700, "#FFFFFF", anchor="middle")
        )
        parts.append(text(x + card_w / 2, y + 74, subtitle, 16, 400, "#D6DEF5", anchor="middle"))
        icon_cx = x + 52
        icon_cy = y + 138
        parts.append(rounded(icon_cx - 30, icon_cy - 30, 60, 60, 16, "#EEF2FF"))
        parts.append(icon_icon(icon, icon_cx, icon_cy, PRIMARY))
        keyword_lines = keywords
        for k, keyword in enumerate(keyword_lines):
            dot_cx = x + 116
            dot_cy = icon_cy - 20 + k * 34
            parts.append(f'<circle cx="{dot_cx:.0f}" cy="{dot_cy:.0f}" r="5" fill="{ACCENT}"/>')
            parts.append(text(dot_cx + 16, dot_cy + 6, keyword, 18, 500, INK))

    # ---------------------------------------------------------------- tech badges
    badge_y = road_y + road_h + 34
    parts.append(text(road_x + 6, badge_y + 26, "TECH STACK", 17, 700, MUTED, spacing="2"))
    bx = road_x + 194
    by = badge_y
    bh = 44
    badge_widths = []
    for badge in TECH_BADGES:
        size = 9 + 8.4 * len(badge)
        badge_widths.append(size)
    total_badges_w = sum(bw + 14 for bw in badge_widths)
    available_w = total_w_of_road - 194
    rows_badges = max(1, int(total_badges_w // available_w) + 1)
    per_row = max(4, int(len(TECH_BADGES) / rows_badges) + (1 if len(TECH_BADGES) % rows_badges else 0))
    x_cursor, y_cursor = bx, by
    count_in_row = 0
    for badge, bw in zip(TECH_BADGES, badge_widths, strict=False):
        if count_in_row >= per_row:
            x_cursor = bx
            y_cursor += bh + 12
            count_in_row = 0
        parts.append(
            f'<rect x="{x_cursor:.0f}" y="{y_cursor:.0f}" width="{bw:.0f}" height="{bh}" rx="{bh // 2}" '
            f'fill="#FFFFFF" stroke="{LINE}" stroke-width="1.5"/>'
        )
        parts.append(
            f'<circle cx="{x_cursor + 16:.0f}" cy="{y_cursor + bh / 2:.0f}" r="5" fill="{SECONDARY}"/>'
        )
        parts.append(text(x_cursor + 30, y_cursor + 29, badge, 17, 600, PRIMARY_LIGHT))
        x_cursor += bw + 14
        count_in_row += 1

    # ---------------------------------------------------------------- timeline
    timeline_y = y_cursor + bh + 74
    parts.append(text(road_x + 6, timeline_y + 6, "DEVELOPMENT TIMELINE", 17, 700, MUTED, spacing="2"))
    tl_x1 = road_x + 6
    tl_x2 = road_x + total_w_of_road - 6
    tl_center = timeline_y + 64
    parts.append(f'<path d="M{tl_x1} {tl_center} H{tl_x2}" stroke="{LINE}" stroke-width="4" fill="none"/>')
    seg = (tl_x2 - tl_x1) / (len(TIMELINE) - 1)
    for i, phase in enumerate(TIMELINE):
        cx = tl_x1 + seg * i
        colour = ACCENT if i == 3 else PRIMARY if i < 3 else SECONDARY
        parts.append(f'<circle cx="{cx:.0f}" cy="{tl_center}" r="12" fill="{colour}"/>')
        parts.append(
            f'<circle cx="{cx:.0f}" cy="{tl_center}" r="20" fill="none" stroke="{colour}" '
            f'stroke-opacity="0.28" stroke-width="3"/>'
        )
        parts.append(text(cx, tl_center + 52, phase, 20, 600, INK, anchor="middle"))

    # ---------------------------------------------------------------- outcomes strip
    outcome_y = timeline_y + 108
    parts.append(text(road_x + 6, outcome_y + 4, "PROJECT OUTCOMES", 17, 700, MUTED, spacing="2"))
    cell_w_o = (total_w_of_road - 5 * 26) // 5
    for i, item in enumerate(OUTCOMES):
        row_index, col_index = divmod(i, 5)
        x = road_x + col_index * (cell_w_o + 26)
        y = outcome_y + 26 + row_index * (62 + 16)
        parts.append(rounded(x, y + 14, cell_w_o, 62, 14, CARD, LINE))
        parts.append(f'<circle cx="{x + 30:.0f}" cy="{y + 45:.0f}" r="6" fill="{SUCCESS}"/>')
        parts.append(text(x + 50, y + 52, item, 19, 600, PRIMARY_LIGHT))

    # ---------------------------------------------------------------- footer
    parts.append(f'<rect x="0" y="{H - 64}" width="{W}" height="64" fill="url(#band)"/>')
    parts.append(
        text(
            70, H - 25, "DEPI - Digital Egypt Pioneers Initiative  |  Graduation Project", 18, 500, "#FFFFFF"
        )
    )
    parts.append(
        text(
            W - 70,
            H - 25,
            "github.com/Ahmedbakr78/Web-to-Warehouse-Product-Intelligence-Pipeline",
            18,
            400,
            "#D6DEF5",
            anchor="end",
        )
    )

    parts.append("</svg>")
    return "\n".join(parts)


def build_html() -> str:
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>Product Intelligence Pipeline - project infographic</title>\n"
        "<style>\n"
        "html,body{margin:0;height:100%;background:#0f172a}\n"
        "body{display:grid;place-items:center;min-height:100vh}\n"
        "main{width:min(96vw, 96vh * 16 / 9);aspect-ratio:16/9;border-radius:18px;overflow:hidden;"
        "box-shadow:0 30px 90px rgba(0,0,0,.5)}\n"
        "svg{width:100%;height:100%;display:block}\n"
        "</style>\n</head>\n<body>\n<main>\n"
        '<object type="image/svg+xml" data="infographic.svg" aria-label="Project infographic slide"></object>\n'
        "</main>\n</body>\n</html>\n"
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    svg = build_svg()
    svg_path = OUT / "infographic.svg"
    svg_path.write_text(svg, encoding="utf-8")
    (OUT / "infographic.html").write_text(build_html(), encoding="utf-8")

    png_path = OUT / "infographic.png"
    try:
        import cairosvg  # type: ignore[import-not-found]

        cairosvg.svg2png(
            bytestring=svg.encode("utf-8"), write_to=str(png_path), output_width=W, output_height=H
        )
    except Exception as exc:  # cairosvg optional - the SVG is the master
        if png_path.exists():
            png_path.unlink()
        print(f"note: PNG export skipped ({type(exc).__name__}); SVG is the master copy")

    print(f"infographic written: {svg_path.relative_to(ROOT)}")
    print(f"preview: {svg_path.with_suffix('.html').relative_to(ROOT)}")
    if png_path.exists():
        print(f"png: {png_path.relative_to(ROOT)}")
    print(f"size: {shutil.get_terminal_size().columns or 80}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
