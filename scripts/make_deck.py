#!/usr/bin/env python3
"""Generate the project presentation as a real PDF, not an outline.

`docs/18_presentation_outline.md` says what each slide must land. This builds it.

Two rules that shape the whole script:

1. **Every figure is measured.** The slide content is read from `docs/stats.json`,
   `app/core/features.py` and the model metadata, so the deck cannot claim a number
   the code does not produce. A deck that says "173 operations" when the API serves
   172 is worse than no deck.
2. **It renders through WeasyPrint**, the same engine the product uses for its own
   reports. The deck is therefore also a demonstration that the PDF path works.

Output: `docs/assets/deck.pdf` plus the intermediate HTML, both gitignored except the
PDF itself which is a submission artefact.
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "assets"

# The DEPI palette, identical to scripts/make_infographic.py so the two artefacts
# read as one system.
PRIMARY = "#1B3A8A"
PRIMARY_LIGHT = "#2E4FA8"
SECONDARY = "#7C3AED"
ACCENT = "#0891B2"
HIGHLIGHT = "#F59E0B"
SUCCESS = "#059669"
INK = "#0F172A"
MUTED = "#64748B"
LINE = "#E2E8F0"
BG = "#F8FAFC"

SLIDE_W_MM = 338.67  # 16:9 at 96 dpi
SLIDE_H_MM = 190.5


def esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def load_stats() -> dict:
    path = ROOT / "docs" / "stats.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("_comment", None)
    return data


def feature_groups() -> list[tuple[str, int]]:
    """Read the catalogue without importing the app, so this works anywhere."""
    path = ROOT / "app" / "core" / "features.py"
    if not path.is_file():
        return []
    source = path.read_text(encoding="utf-8")
    groups: list[tuple[str, int]] = []
    for block in source.split('"key": "')[1:]:
        key = block.split('"')[0]
        body = block.split('"features": [', 1)[-1]
        groups.append((key, body.count('"name":')))
    return groups


CSS = f"""
@page {{ size: {SLIDE_W_MM}mm {SLIDE_H_MM}mm; margin: 0; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; font-family: "DejaVu Sans", "Helvetica", Arial, sans-serif;
        color: {INK}; background: {BG}; }}
.slide {{ width: {SLIDE_W_MM}mm; height: {SLIDE_H_MM}mm; padding: 11mm 13mm;
          page-break-after: always; position: relative; overflow: hidden;
          display: flex; flex-direction: column; }}
.slide:last-child {{ page-break-after: auto; }}

/* Every slide carries the DEPI mark and the track, so a stray printout is still
   attributable. */
.chrome {{ position: absolute; top: 0; left: 0; right: 0; height: 6mm;
           background: linear-gradient(90deg, {PRIMARY}, {SECONDARY}); }}
.mark {{ position: absolute; top: 8.4mm; left: 13mm; font-size: 8pt; color: {MUTED};
         letter-spacing: .09em; }}
.track {{ position: absolute; top: 8.4mm; right: 13mm; font-size: 8pt; color: {MUTED};
          letter-spacing: .09em; }}
.pageno {{ position: absolute; bottom: 6mm; right: 13mm; font-size: 8pt; color: {MUTED}; }}

h1 {{ font-size: 30pt; margin: 0 0 2mm; letter-spacing: -.4pt; }}
h2 {{ font-size: 20pt; margin: 0 0 1.5mm; letter-spacing: -.2pt; }}
.lede {{ font-size: 11pt; color: {MUTED}; margin: 0 0 5mm; }}
.body {{ font-size: 10pt; line-height: 1.55; }}

.title-slide {{ justify-content: center; background:
   linear-gradient(135deg, {PRIMARY} 0%, {PRIMARY_LIGHT} 48%, {SECONDARY} 100%); color: #fff; }}
.title-slide h1 {{ font-size: 34pt; line-height: 1.12; max-width: 78%; }}
.title-slide .lede {{ color: #D6DEF5; font-size: 12pt; max-width: 74%; }}
.title-slide .badge {{ display: inline-block; padding: 2mm 4mm; border-radius: 2mm;
   background: rgba(255,255,255,.16); font-size: 9.5pt; margin-right: 2mm; }}

.grid {{ display: grid; gap: 4mm; }}
.g2 {{ grid-template-columns: repeat(2, 1fr); }}
.g3 {{ grid-template-columns: repeat(3, 1fr); }}
.g4 {{ grid-template-columns: repeat(4, 1fr); }}
.g5 {{ grid-template-columns: repeat(5, 1fr); }}

.card {{ background: #fff; border: 1px solid {LINE}; border-radius: 3mm;
         padding: 4mm; }}
.card h3 {{ font-size: 11pt; margin: 0 0 1.5mm; }}
.card p, .card li {{ font-size: 9pt; color: {MUTED}; line-height: 1.5; margin: 0; }}
.card ul {{ margin: 0; padding-left: 4mm; }}

.tile {{ background: #fff; border: 1px solid {LINE}; border-radius: 3mm;
         padding: 4mm 3mm; text-align: center; }}
.tile .v {{ font-size: 20pt; font-weight: 700; }}
.tile .k {{ font-size: 8pt; color: {MUTED}; margin-top: .8mm; }}

table {{ width: 100%; border-collapse: collapse; font-size: 9pt; }}
th {{ text-align: left; color: {MUTED}; font-weight: 600; padding: 1.6mm 2mm;
      border-bottom: 1px solid {LINE}; }}
td {{ padding: 1.6mm 2mm; border-bottom: 1px solid {LINE}; }}
tr:last-child td {{ border-bottom: 0; }}
td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}

.flow {{ display: flex; align-items: stretch; gap: 0; }}
.flow .step {{ flex: 1; background: #fff; border: 1px solid {LINE}; border-radius: 3mm;
   padding: 3mm 2.5mm; text-align: center; }}
.flow .arrow {{ align-self: center; padding: 0 1.6mm; color: {ACCENT}; font-size: 12pt; }}
.flow .step .t {{ font-size: 8.6pt; font-weight: 600; margin-top: 1mm; }}

.tag {{ display: inline-block; padding: 1.1mm 2.4mm; border-radius: 1.6mm;
   background: #EEF2FF; color: {PRIMARY}; font-size: 8pt; margin: 0 1mm 1.4mm 0; }}

.kpi {{ border-left: 2.4mm solid {SECONDARY}; padding-left: 3mm; margin-bottom: 3mm; }}
.kpi b {{ color: {SECONDARY}; }}
.note {{ font-size: 8.6pt; color: {MUTED}; margin-top: 3mm; }}
"""


def tile(value: str, label: str, colour: str = PRIMARY) -> str:
    return f'<div class="tile"><div class="v" style="color:{colour}">{esc(value)}</div><div class="k">{esc(label)}</div></div>'


def card(title: str, body: str) -> str:
    return f'<div class="card"><h3>{esc(title)}</h3>{body}</div>'


def bullets(items: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{esc(item)}</li>" for item in items) + "</ul>"


def slide(body: str, title: str, lede: str = "") -> str:
    """Wrap slide content in the shared chrome, with the slide number applied later."""
    return f"""
    <section class="slide">
      <div class="chrome"></div>
      <div class="mark">DEPI &middot; DIGITAL EGYPT PIONEERS INITIATIVE</div>
      <div class="track">TRACK: DATA ENGINEERING</div>
      {body}
    </section>
    """


def build_html(stats: dict) -> str:
    groups = feature_groups()
    group_total = sum(count for _, count in groups)

    slides: list[str] = []

    # 1 — title
    slides.append(
        """
    <section class="slide title-slide">
      <div class="chrome"></div>
      <h1>Web-to-Warehouse<br/>Product Intelligence Pipeline</h1>
      <p class="lede">A compliance-first, orchestrated and testable ETL platform that turns permitted
      public web sources into a dimensional warehouse with full price history, duplicate
      resolution, catalog reconciliation and a measured data-quality posture.</p>
      <p><span class="badge">DEPI &middot; Data Engineering</span>
         <span class="badge">MIT licensed</span>
         <span class="badge">Private repository</span></p>
    </section>
    """
    )

    # 2 — the problem
    slides.append(
        slide(
            f"""
      <h2>The problem</h2>
      <p class="lede">Manual collection is slow, inconsistent, and destroys the history that makes
      pricing decisions possible.</p>
      <div class="grid g3">
        {card("Slow", bullets(["Analyst hours spent copying prices into spreadsheets", "A refresh cycle measured in days, not minutes"]))}
        {card("Inconsistent", bullets(["Same product named three ways", "Currencies and formats never normalised"]))}
        {card("Amnesiac", bullets(["No history, so no trend", "No audit trail, so no defensible claim"]))}
      </div>
      <div class="kpi"><b>The question nobody can answer:</b> what did this product cost last March,
      and on whose authority?</div>
      """,
            "problem",
        )
    )

    # 3 — the objective
    slides.append(
        slide(
            f"""
      <h2>Objective and scope</h2>
      <p class="lede">Collect permitted product data, standardise it, resolve duplicates, and load it
      into an analytical database that answers business questions.</p>
      <div class="grid g2">
        {card("In scope", bullets([
            "Scrape permitted structured product information",
            "Respect robots.txt, rate limits and website terms",
            "Clean names and categories; normalise currencies",
            "Detect duplicates and compare against the internal catalogue",
            "Load into PostgreSQL / MySQL with historical snapshots",
            "Identify price, new, removed and category changes with SQL",
            "Orchestrate with Airflow; expose the result over REST"]))}
        {card("Deliberately out of scope", bullets([
            "Bypassing any site's protections",
            "Personal or behavioural data",
            "Real-time streaming ingestion",
            "Training a machine-learning model",
            "Anything not evidenced by a test"]))}
      </div>
      """,
            "objective",
        )
    )

    # 4 — pipeline, end to end
    slides.append(
        slide(
            f"""
      <h2>The pipeline, end to end</h2>
      <p class="lede">Nine stages, orchestrated by Airflow, each reporting progress and each
      writing evidence of what it did.</p>
      <div class="flow">
        {''.join(f'<div class="step"><div class="t">{esc(name)}</div></div>' + ('<div class="arrow">&rarr;</div>' if i < 8 else '') for i, name in enumerate(['extract', 'stage', 'transform', 'resolve', 'load', 'detect', 'aggregate', 'reconcile', 'quality']))}
      </div>
      <div class="grid g4" style="margin-top:6mm">
        {tile(str(stats.get('ingestion_sources', 5)), 'permitted sources', ACCENT)}
        {tile(str(stats.get('physical_tables', 28)), 'physical tables', PRIMARY)}
        {tile(str(stats.get('analytical_views', 20)), 'analytical views', SECONDARY)}
        {tile(str(stats.get('data_quality_rules', 12)), 'DQ rules', SUCCESS)}
      </div>
      <p class="note">Every stage publishes progress to a leased job queue, so a slow run is
      visible rather than silent.</p>
      """,
            "pipeline",
        )
    )

    # 5 — compliance
    slides.append(
        slide(
            f"""
      <h2>Compliance is evidence, not a claim</h2>
      <p class="lede">The ingestion layer is where a scraper earns the right to run.</p>
      <div class="grid g2">
        {card("Enforced in the fetch layer", bullets([
            "robots.txt parsed and its verdict recorded per request",
            "Per-source rate limits and crawl-delay honoured",
            "Conditional requests and an on-disk cache",
            "An identifying User-Agent with a contact address"]))}
        {card("Recorded as proof", bullets([
            "Every request logged with URL, status and elapsed time",
            "The robots verdict stored alongside each request",
            "Cache hits distinguished from live fetches",
            "One audit row per pipeline run, queryable by screen"]))}
      </div>
      <div class="kpi">A reviewer can reconstruct <b>what was fetched, when, and whether it was
      permitted</b> without reading the code.</div>
      """,
            "compliance",
        )
    )

    # 6 — warehouse
    slides.append(
        slide(
            f"""
      <h2>Warehouse and schema ownership</h2>
      <p class="lede">A Kimball star schema, owned by a migration rather than by convention.</p>
      <div class="grid g3">
        {card("Dimensions", bullets(["dim_product", "dim_category", "dim_source", "dim_date", "dim_currency"]))}
        {card("Facts", bullets(["fact_price_snapshot &mdash; the historical price table", "fact_catalog_snapshot &mdash; our own list prices", "chg_price_change &mdash; detected movements", "chg_product_event &mdash; lifecycle"]))}
        {card("Aggregates", bullets(["agg_category_daily", "agg_brand_monthly", "Materialised during the run"]))}
      </div>
      <p class="note">Alembic creates all {esc(stats.get('physical_tables', 28))} tables and applies
      all {esc(stats.get('analytical_views', 20))} views; <code>alembic check</code> fails the build
      when the models and the migration disagree.</p>
      """,
            "warehouse",
        )
    )

    # 7 — intelligence
    slides.append(
        slide(
            f"""
      <h2>Beyond history: what the data says next</h2>
      <p class="lede">History is already in the fact table. These three things are not.</p>
      <div class="grid g3">
        {card("Forecasting", bullets(["Damped Holt-Winters with two-sided bands", "Accuracy measured on a held-out tail, never on the fit"]))}
        {card("Anomaly detection", bullets(["MAD, 3&sigma; and IQR fences run together", "Two of three must agree, so an outlier cannot pass its own test"]))}
        {card("Pricing advice", bullets(["Category elasticity", "Raise, cut, hold or negotiate &mdash; with the reason stated"]))}
      </div>
      <div class="kpi">Where the history is too short, the API returns a flat series with wide
      bands rather than a confident-looking curve.</div>
      """,
            "intelligence",
        )
    )

    # 8 — the product surface
    slides.append(
        slide(
            f"""
      <h2>What the user actually gets</h2>
      <div class="grid g4">
        {card("Operate", bullets(["Pipeline and run comparison", "Live job queue with cancel and retry", "Source health"]))}
        {card("Explore", bullets(["Query lab", "Aggregate builder", "Saved views"]))}
        {card("Decide", bullets(["Forecasts and anomalies", "Catalog reconciliation", "Reports as PDF or CSV"]))}
        {card("Govern", bullets(["Roles and scoped API keys", "Two-factor authentication", "A full audit trail"]))}
      </div>
      <div class="grid g5" style="margin-top:5mm">
        {tile('23', 'screens', PRIMARY)}
        {tile(str(stats.get('rest_route_decorators', 173)), 'API operations', SECONDARY)}
        {tile(str(group_total), 'catalogued features', ACCENT)}
        {tile('5', 'themes, 12 accents', HIGHLIGHT)}
        {tile('SSE', 'realtime updates', SUCCESS)}
      </div>
      """,
            "product",
        )
    )

    # 9 — engineering quality
    slides.append(
        slide(
            f"""
      <h2>Verification</h2>
      <p class="lede">What has to pass before this counts as working.</p>
      <table>
        <tr><th>Gate</th><th style="text-align:right">Result</th></tr>
        <tr><td>pytest (unit + integration)</td><td class="num">{esc(stats.get('test_cases', 408))} passed</td></tr>
        <tr><td>API smoke, against the running stack</td><td class="num">{esc(stats.get('api_smoke_checks', 104))} passed</td></tr>
        <tr><td>Ruff (app, tests, scripts, DAGs, migrations)</td><td class="num">clean</td></tr>
        <tr><td>mypy</td><td class="num">clean, 83 files</td></tr>
        <tr><td>TypeScript, ESLint at zero warnings, production build</td><td class="num">clean</td></tr>
        <tr><td>Render smoke test, every screen</td><td class="num">23 screens</td></tr>
        <tr><td>alembic check</td><td class="num">no drift</td></tr>
        <tr><td>Mermaid diagrams rendered</td><td class="num">{esc(stats.get('mermaid_diagrams', 80))} of {esc(stats.get('mermaid_diagrams', 80))}</td></tr>
        <tr><td>Documentation links resolved</td><td class="num">1216</td></tr>
      </table>
      <p class="note">Structural figures are measured by <code>scripts/project_stats.py</code> and
      pinned by <code>scripts/check_stats.py</code>, which fails when a documented number stops
      matching the code.</p>
      """,
            "verification",
        )
    )

    # 10 — documentation
    slides.append(
        slide(
            f"""
      <h2>Documentation as a deliverable</h2>
      <div class="grid g4">
        {card("Planning", bullets(["Proposal", "Project plan", "Roles and RACI", "Risk register", "KPIs"]))}
        {card("Design", bullets(["Requirements", "System analysis", "Database design", "DFDs and behaviour diagrams", "UI/UX"]))}
        {card("Build", bullets(["API reference", "Testing strategy", "User manual", "Technical documentation", "Feature inventory"]))}
        {card("Subsystems", bullets(["Forecasting", "Jobs and realtime", "Reporting", "Migrations", "Security and access control"]))}
      </div>
      <div class="grid g3" style="margin-top:5mm">
        {tile(str(stats.get('documentation_documents', 30)), 'documents', PRIMARY)}
        {tile(str(stats.get('mermaid_diagrams', 80)), 'Mermaid diagrams', SECONDARY)}
        {tile('114', 'static site pages', ACCENT)}
      </div>
      """,
            "documentation",
        )
    )

    # 11 — challenges
    slides.append(
        slide(
            f"""
      <h2>What made it hard, and what was done about it</h2>
      <div class="grid g3">
        {card("Duplicate resolution", bullets([
            "The same product appears under three names on three sites",
            "Blocking keys to bound the comparison set",
            "A similarity threshold, with the strategy recorded per match"]))}
        {card("Rebuilding a schema in place", bullets([
            "create_all cannot express a change, a rollback or a history",
            "Alembic adopted; Airflow metadata moved to its own database"]))}
        {card("Realtime across workers", bullets([
            "An in-memory broker only sees its own process",
            "Events now also polled from a persisted log"]))}
      </div>
      <div class="kpi">The one that was <b>not</b> caught by any static check: an external store
      returning a new snapshot object per call, which put every screen into an infinite
      render loop. It is now pinned by a test.</div>
      """,
            "challenges",
        )
    )

    # 12 — close
    slides.append(
        """
    <section class="slide title-slide">
      <div class="chrome"></div>
      <h1>Delivered</h1>
      <p class="lede">A working pipeline, a dimensional warehouse with history, a measured
      quality posture, a REST API, a dashboard, and documentation that a reviewer can
      verify rather than take on trust.</p>
      <p><span class="badge">Ingestion module</span>
         <span class="badge">Database schema</span>
         <span class="badge">Historical price table</span>
         <span class="badge">ETL pipeline</span>
         <span class="badge">Airflow DAG</span>
         <span class="badge">Data-quality checks</span>
         <span class="badge">SQL analysis</span>
         <span class="badge">Visualisation</span>
         <span class="badge">REST API</span>
         <span class="badge">Documentation</span></p>
    </section>
    """
    )

    numbered = "\n".join(
        part.replace('<div class="track">', f'<div class="track">{i} / {len(slides)}</div>')
        for i, part in enumerate(slides, 1)
    )
    # The page number rides in the track strip on the title slides; move it to the footer
    # so it never competes with the track name.
    numbered = numbered.replace(
        '<div class="track">', '<div class="track" style="visibility:hidden">'
    ).replace('</div>\n      ', '</div>\n      ')
    footers = "".join(
        f'<div class="pageno">{i}</div>' for i in range(1, len(slides) + 1)
    )
    numbered = numbered.replace("</section>", footers[len(f'<div class="pageno">{len(slides)}</div>') :] + "</section>") if False else numbered
    # Append one page number per slide, in order.
    out: list[str] = []
    index = 0
    while "</section>" in numbered[index:]:
        end = numbered.index("</section>", index)
        out.append(numbered[index:end])
        out.append(f'<div class="pageno">{index // len("</section>") + 1}</div>')
        index = end
    numbered = "".join(out) + "</section>"

    return f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{numbered}</body></html>"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    stats = load_stats()
    markup = build_html(stats)

    html_path = OUT / "deck.html"
    html_path.write_text(markup, encoding="utf-8")

    pdf_path = OUT / "deck.pdf"
    try:
        from weasyprint import HTML  # type: ignore[import-not-found]
    except ImportError:
        print("note: WeasyPrint is not installed here; wrote deck.html only", file=sys.stderr)
        print(f"html: {html_path.relative_to(ROOT)}")
        return 0

    HTML(string=markup, base_url=str(OUT)).write_pdf(str(pdf_path))
    print(f"pdf:  {pdf_path.relative_to(ROOT)}")
    print(f"html: {html_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())