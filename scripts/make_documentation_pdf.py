#!/usr/bin/env python3
"""Generate an up-to-date consolidated project documentation PDF via WeasyPrint.

Reads live metrics from ``docs/stats.json``, ``VERSION``, and the structured
chapters in ``docs/``, rendering a cohesive multi-chapter PDF whose numbers
match the current repository state.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

CHAPTERS = [
    ("00_team.md", "Team, Roles & Effort Split"),
    ("01_project_proposal.md", "Project Planning — Proposal"),
    ("02_project_plan.md", "Project Plan & Schedule"),
    ("03_roles_and_responsibilities.md", "Roles & RACI Matrix"),
    ("04_risk_assessment.md", "Risk Assessment & Mitigation"),
    ("05_kpis.md", "Key Performance Indicators"),
    ("06_literature_review.md", "Literature Review"),
    ("07_requirements_gathering.md", "Requirements Gathering"),
    ("08_system_analysis_design.md", "System Analysis & Design"),
    ("15_testing_strategy.md", "Testing & Quality Assurance"),
]


def _load_stats() -> dict[str, int]:
    path = ROOT / "docs" / "stats.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if isinstance(v, int)}


def _render_pdf(output_paths: list[Path]) -> None:
    import build_site
    from weasyprint import HTML

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    stats = _load_stats()
    today = dt.date.today().isoformat()

    sections_html: list[str] = []
    diagram_dir = ROOT / "docs" / "diagrams" / "out"
    for filename, label in CHAPTERS:
        md_path = ROOT / "docs" / filename
        if not md_path.is_file():
            continue
        raw = md_path.read_text(encoding="utf-8")
        rendered = build_site.render_markdown(raw)
        svgs = sorted(diagram_dir.glob(f"docs-{Path(filename).stem}_*.svg"))
        svg_iter = iter(svgs)

        def _replace_mermaid(_match: re.Match[str], it=svg_iter) -> str:
            svg = next(it, None)
            if svg is None:
                return ""
            return (
                f'<div class="diagram-box"><img src="{html.escape(str(svg.resolve()))}" '
                f'alt="{html.escape(svg.stem)}" style="max-width:100%;max-height:175mm;"/></div>'
            )

        body_html = re.sub(r'<pre class="mermaid">.*?</pre>', _replace_mermaid, rendered.body, flags=re.S)
        sections_html.append(
            f'<section class="chapter"><div class="chapter-kicker">{html.escape(filename)} · {html.escape(label)}</div>'
            f"{body_html}</section>"
        )

    cover = f"""
    <section class="cover">
      <div class="eyebrow">DEPI — DIGITAL EGYPT PIONEERS INITIATIVE · DATA ENGINEERING TRACK</div>
      <h1>Web-to-Warehouse<br/>Product Intelligence Pipeline</h1>
      <p class="subtitle">Consolidated Technical &amp; Engineering Documentation</p>
      <div class="meta-box">
        <div><strong>Team Leader:</strong> Ahmed Abobakr (78102) — @Ahmedbakr78</div>
        <div><strong>Repository:</strong> github.com/Ahmedbakr78/Web-to-Warehouse-Product-Intelligence-Pipeline</div>
        <div><strong>Version:</strong> v{html.escape(version)} · <strong>Generated:</strong> {today}</div>
        <div><strong>Verified Stack:</strong>
          {stats.get("physical_tables", 29)} tables ·
          {stats.get("analytical_views", 23)} views ·
          {stats.get("rest_routers", 24)} routers ({stats.get("rest_route_decorators", 222)} REST ops) ·
          {stats.get("ingestion_sources", 34)} sources ·
          {stats.get("data_quality_rules", 12)} DQ rules ·
          {stats.get("test_cases", 634)} backend tests ·
          {stats.get("catalogued_features", 767)} features
        </div>
      </div>
    </section>
    """

    full_html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Web-to-Warehouse Product Intelligence Pipeline Documentation v{html.escape(version)}</title>
<style>
  @page {{
    size: A4;
    margin: 18mm 16mm 18mm 16mm;
    @bottom-right {{
      content: "Page " counter(page) " of " counter(pages);
      font-size: 8.5pt;
      color: #64748b;
    }}
    @bottom-left {{
      content: "Product Intelligence Pipeline v{html.escape(version)}";
      font-size: 8.5pt;
      color: #64748b;
    }}
  }}
  body {{
    font-family: Inter, "DejaVu Sans", Arial, sans-serif;
    font-size: 9.5pt;
    line-height: 1.5;
    color: #0f172a;
  }}
  .cover {{
    page-break-after: always;
    padding-top: 40mm;
  }}
  .eyebrow {{
    font-size: 8.5pt;
    font-weight: 700;
    letter-spacing: 0.12em;
    color: #4f46e5;
    margin-bottom: 12pt;
  }}
  h1 {{
    font-size: 24pt;
    line-height: 1.15;
    margin: 0 0 8pt 0;
    color: #1e293b;
  }}
  .subtitle {{
    font-size: 13pt;
    color: #475569;
    margin: 0 0 24pt 0;
  }}
  .meta-box {{
    background: #f8fafc;
    border: 1px solid #cbd5e1;
    border-left: 4px solid #4f46e5;
    border-radius: 6pt;
    padding: 12pt 14pt;
    font-size: 9.5pt;
    line-height: 1.7;
  }}
  .chapter {{
    page-break-before: always;
  }}
  .chapter-kicker {{
    font-size: 8pt;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #6366f1;
    margin-bottom: 4pt;
  }}
  h2 {{
    font-size: 13pt;
    color: #1e293b;
    border-bottom: 1px solid #e2e8f0;
    padding-bottom: 3pt;
    margin-top: 14pt;
  }}
  h3 {{
    font-size: 10.5pt;
    color: #334155;
    margin-top: 10pt;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 8pt 0 12pt 0;
    font-size: 8pt;
    table-layout: fixed;
    word-wrap: break-word;
  }}
  th, td {{
    border: 1px solid #cbd5e1;
    padding: 4pt 6pt;
    text-align: left;
    vertical-align: top;
  }}
  th {{
    background: #f1f5f9;
    font-weight: 700;
  }}
  pre, code {{
    font-family: "DejaVu Sans Mono", monospace;
    font-size: 8pt;
    background: #f1f5f9;
    border-radius: 3pt;
  }}
  pre {{
    padding: 8pt;
    white-space: pre-wrap;
    border: 1px solid #e2e8f0;
  }}
  .mermaid-card {{
    display: none;
  }}
</style>
</head>
<body>
{cover}
{"".join(sections_html)}
</body>
</html>
"""
    for out in output_paths:
        out.parent.mkdir(parents=True, exist_ok=True)
        HTML(string=full_html, base_url=str(ROOT / "docs")).write_pdf(str(out))
        print(f"wrote PDF: {out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    _render_pdf(
        [
            ROOT / "docs" / "assets" / "Project_Documentation.pdf",
            ROOT / "Web-to-Warehouse-Product-Intelligence-Pipeline_Documentation.pdf",
        ]
    )
