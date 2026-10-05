"""Build a self-contained documentation website from the Markdown in ``docs/``.

Why hand-rolled instead of MkDocs? Three reasons that matter for this repository:

1. **Zero dependencies.** ``python3 scripts/build_site.py`` works on a bare Python 3 install.
   MkDocs and its Material theme would add a large dependency tree for a build that is
   fundamentally markdown -> HTML plus a navigation shell.
2. **Private-repo friendly.** GitHub Pages does not serve private repositories on the free plan, so
   a Pages workflow would be dead on arrival here. This build produces a plain directory of static
   files that can be served locally, dropped on any static host, or attached to a release.
3. **Faithful rendering.** The documentation is written with GitHub-flavoured Mermaid fenced
   blocks and GitHub-style tables. This builder understands exactly those two constructs, so the
   output matches what the README already shows on github.com.

The result is written to ``site/``: one HTML page per document, a landing page, a client-side
search index, and a copy of the Mermaid runtime for offline rendering.

Usage::

    python3 scripts/build_site.py                # build into ./site
    python3 scripts/build_site.py --out dist     # build elsewhere
    python3 scripts/build_site.py --serve        # build, then serve on :8001
"""

from __future__ import annotations

import argparse
import contextlib
import html
import json
import re
import shutil
import webbrowser
from dataclasses import dataclass, field
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SITE_VERSION = "1.3.0"

# --------------------------------------------------------------------------- config

TITLE = "Web-to-Warehouse Product Intelligence Pipeline"
SUBTITLE = "Compliant web ingestion, a Kimball warehouse on two SQL dialects, and a dashboard"
AUTHOR = "Ahmed Abobakr"

#: Mermaid is loaded from the CDN when online, with a local copy preferred when present.
MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs"
MERMAID_LOCAL = "vendor/mermaid.esm.min.mjs"

#: Ordered navigation. Each entry is (filename, title, blurb).
NAV: list[tuple[str, str, str]] = [
    ("README.md", "Overview", "What the project is and how to run it"),
    ("01_project_proposal.md", "Project Proposal", "Problem, objectives, scope, stakeholders, ethics"),
    ("02_project_plan.md", "Project Plan", "Twelve-week schedule, milestones, deliverables"),
    ("03_roles_and_responsibilities.md", "Roles and Responsibilities", "Team roles, RACI, hours log"),
    ("04_risk_assessment.md", "Risk Assessment", "Twenty-risk register, heat map, treatments"),
    ("05_kpis.md", "KPIs", "Twenty KPIs with runnable SQL and measured values"),
    ("06_literature_review.md", "Literature Review", "Six themes, verified sources, synthesis"),
    ("07_requirements_gathering.md", "Requirements", "User stories, use cases, 84 requirements"),
    ("08_system_analysis_design.md", "System Analysis and Design", "Use cases, architecture, rationale"),
    ("09_database_design.md", "Database Design", "23-table ERD, indexing, retention"),
    ("10_data_flow_diagrams.md", "Data Flow Diagrams", "Level 0/1/2 DFDs, data dictionary"),
    ("11_behaviour_diagrams.md", "Behaviour Diagrams", "Sequence, activity, state, class"),
    ("12_ui_ux_design.md", "UI/UX Design", "Wireframes, design system, WCAG 2.1 AA"),
    ("13_deployment.md", "Deployment", "Stack, environments, CI/CD, backups"),
    ("14_api_documentation.md", "API Documentation", "Auth, roles, all 113 operations, examples"),
    ("15_testing_strategy.md", "Testing Strategy", "Test pyramid, 100-case plan, quality gates"),
    ("16_user_manual.md", "User Manual", "Every screen, filters, exports, troubleshooting"),
    ("17_technical_documentation.md", "Technical Documentation", "Module map, algorithms, config"),
    ("18_presentation_outline.md", "Presentation Outline", "Defence deck, Q&A, demo script"),
    ("19_feature_list.md", "Feature Inventory", "234 features with file references"),
    ("20_literature_feedback_and_improvements.md", "Feedback and Improvements", "Prioritised next steps"),
    ("21_architecture_deep_dive.md", "Architecture Deep Dive", "Decisions, trade-offs, request lifecycle"),
    ("22_data_dictionary.md", "Data Dictionary", "Every table, column, type and meaning"),
    ("23_glossary_and_faq.md", "Glossary and FAQ", "Terms defined, questions answered"),
    ("24_demo_runbook.md", "Demo Runbook", "Screen-by-screen live demo script and failure playbook"),
]

#: Documents grouped for the sidebar; keys render as section headers.
NAV_GROUPS: list[tuple[str, list[str]]] = [
    ("Start here", ["README.md", "21_architecture_deep_dive.md"]),
    (
        "Project lifecycle",
        [
            "01_project_proposal.md",
            "02_project_plan.md",
            "03_roles_and_responsibilities.md",
            "04_risk_assessment.md",
            "05_kpis.md",
            "06_literature_review.md",
            "07_requirements_gathering.md",
        ],
    ),
    (
        "Design",
        [
            "08_system_analysis_design.md",
            "09_database_design.md",
            "10_data_flow_diagrams.md",
            "11_behaviour_diagrams.md",
            "12_ui_ux_design.md",
            "13_deployment.md",
        ],
    ),
    (
        "Build and operate",
        [
            "14_api_documentation.md",
            "15_testing_strategy.md",
            "16_user_manual.md",
            "17_technical_documentation.md",
            "18_presentation_outline.md",
            "19_feature_list.md",
            "20_literature_feedback_and_improvements.md",
            "22_data_dictionary.md",
            "23_glossary_and_faq.md",
            "24_demo_runbook.md",
        ],
    ),
]

STATS = [
    ("23", "physical tables"),
    ("20", "analytical views"),
    ("113", "REST operations"),
    ("12", "data-quality rules"),
    ("5", "ingestion sources"),
    ("13", "Airflow tasks"),
    ("255", "unit tests"),
    ("78", "API smoke checks"),
]

PIPELINE_STEPS = [
    (
        "Retrieve",
        "robots.txt gate, token-bucket rate limit, circuit breaker, response cache, per-request audit",
    ),
    ("Clean", "29 normalisation steps, 18+ currency formats, offline FX table, fixed vocabularies"),
    ("Load", "resumable staging, then idempotent dimension and fact merges on natural keys"),
    ("Detect", "price changes banded by magnitude, new/removed/recategorised events, catalog reconciliation"),
    ("Quality", "12 rules across 6 dimensions, weighted score persisted per run, 90-day trend"),
    ("Serve", "113 REST operations, 20 dashboard screens, CSV/JSON exports, read-only query lab"),
]

QUICKSTART = [
    (
        "Bring the stack up",
        "make up && make db-wait",
        "PostgreSQL 16, MySQL 8.4, the API, Airflow and the dashboard",
    ),
    ("Create the schema", "make bootstrap", "23 tables, 20 views, demo users and reference data"),
    ("Load the demo dataset", "make demo-postgres", "130 products and 150 days of price history"),
    ("Run the pipeline", "make run-pipeline", "Ingest, clean, load, detect changes and score quality"),
    ("Open the dashboard", "open http://localhost:5173", "admin@example.com / Admin@12345"),
    ("Verify everything", "make check", "ruff, mypy and the 255-test suite"),
]


# --------------------------------------------------------------------------- markdown


@dataclass
class Rendered:
    """Result of converting one Markdown file."""

    body: str
    headings: list[tuple[int, str, str]] = field(default_factory=list)
    plain: str = ""


def slugify(text: str) -> str:
    """Heading anchor, reproducing GitHub's ``github-slugger`` exactly.

    The documents link to their own headings with hand-written anchors, so an
    approximation is not good enough -- a mismatch silently breaks every in-page
    link. The algorithm below was verified case-for-case against the
    ``github-slugger`` package GitHub itself uses, including the awkward parts:

    * whitespace is replaced **one character at a time**, not collapsed, so three
      spaces become three hyphens (``multiple---spaces``);
    * removed punctuation leaves the hyphens it was sitting between, so
      ``"sequence — one"`` keeps the **double** hyphen;
    * underscores survive, because they are word characters;
    * nothing is stripped at any stage: ``"  spaced  "`` becomes ``--spaced--``
      and ``"!!!bang!!!"`` becomes ``bang``.

    ``scripts/check_slugify.py`` re-verifies this against the reference
    implementation; do not "tidy" this without running it.
    """
    slug = text.lower()
    slug = re.sub(r"[^\w\s-]", "", slug, flags=re.UNICODE)
    return re.sub(r"\s", "-", slug)


def _rewrite_href(url: str) -> str:
    """Point a Markdown link at the generated HTML page instead of the source file.

    Documents cross-reference each other with ``](01_project_proposal.md)`` links because that is
    what works on github.com. In the built site the same link must resolve to
    ``01_project_proposal.html``.
    """
    if url.startswith(("http://", "https://", "mailto:", "#", "data:")):
        return url
    path, sep, frag = url.partition("#")
    if not path.endswith(".md"):
        return url
    target = path[:-3].lower() + ".html"
    return target + (sep + frag if sep else "")


def _inline(text: str) -> str:
    """Convert the inline Markdown constructs used throughout these documents."""
    out = html.escape(text, quote=False)
    # `code`
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    # images: ![alt](src)
    out = re.sub(
        r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)",
        lambda m: (
            f'<img src="{m.group(2)}" alt="{m.group(1)}" loading="lazy">'
            if not m.group(2).endswith(".svg")
            else f'<object class="diagram-object" data="{m.group(2)}" type="image/svg+xml"></object>'
        ),
        out,
    )
    # links
    out = re.sub(
        r"\[([^\]]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)",
        lambda m: f'<a href="{_rewrite_href(m.group(2))}">{m.group(1)}</a>',
        out,
    )
    # bold, italic (bold first so *** does not collide)
    out = re.sub(r"\*\*\*([^*]+)\*\*\*", r"<strong><em>\1</em></strong>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?!\w)", r"<em>\1</em>", out)
    # strikethrough
    out = re.sub(r"~~([^~]+)~~", r"<del>\1</del>", out)
    # bare autolinks -- a lambda, because \0 in a replacement would emit a NUL byte
    out = re.sub(
        r"(?<![\"'=>#])\bhttps?://[^\s<)]+",
        lambda m: f'<a href="{m.group(0)}">{m.group(0)}</a>',
        out,
    )
    return out


def _table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _split_row(line: str) -> str:
    return line.strip().strip("|").strip()


def render_markdown(text: str) -> Rendered:
    """Convert GitHub-flavoured Markdown (headings, tables, fences, lists) to HTML.

    Supported deliberately: what these twenty-odd documents actually use. Anything unrecognised
    falls through as a paragraph rather than vanishing, so a construct is never silently dropped.
    """
    lines = text.split("\n")
    out: list[str] = []
    headings: list[tuple[int, str, str]] = []
    plain_parts: list[str] = []
    seen_ids: dict[str, int] = {}

    i = 0
    n = len(lines)
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # ---- fenced code / mermaid -------------------------------------------
        fence = re.match(r"^(`{3,}|~{3,})\s*([\w+-]*)\s*$", stripped)
        if fence:
            close_list()
            lang = fence.group(2).lower()
            body: list[str] = []
            i += 1
            while i < n and not re.match(r"^\s*[`~]{3,}\s*$", lines[i]):
                body.append(lines[i])
                i += 1
            i += 1
            content = "\n".join(body)
            plain_parts.append(content)
            if lang == "mermaid":
                out.append(f'<pre class="mermaid">{html.escape(content)}</pre>')
            else:
                out.append(
                    f'<pre class="code" data-lang="{html.escape(lang)}">'
                    f"<code>{html.escape(content)}</code></pre>"
                )
            continue

        # ---- table -------------------------------------------------------------
        if stripped.startswith("|") and i + 1 < n and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            close_list()
            header = _table_row(lines[i])
            i += 2  # skip header and separator
            rows: list[list[str]] = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(_table_row(lines[i]))
                i += 1
            out.append("<div class='table-scroll'><table><thead><tr>")
            for cell in header:
                out.append(f"<th>{_inline(cell)}</th>")
            out.append("</tr></thead><tbody>")
            for row in rows:
                out.append("<tr>")
                for idx, cell in enumerate(row):
                    tag = "th" if idx == 0 and len(cell) <= 24 else "td"
                    out.append(f"<{tag}>{_inline(cell)}</{tag}>")
                out.append("</tr>")
            out.append("</tbody></table></div>")
            plain_parts.append(" ".join(header))
            continue

        # ---- headings ----------------------------------------------------------
        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            close_list()
            level = len(heading.group(1))
            raw = re.sub(r"[#*`]", "", heading.group(2)).strip()
            base = slugify(raw)
            count = seen_ids.get(base, 0)
            seen_ids[base] = count + 1
            anchor = base if count == 0 else f"{base}-{count}"
            headings.append((level, raw, anchor))
            out.append(f'<h{level} id="{anchor}">{_inline(heading.group(2))}</h{level}>')
            if level <= 3:
                plain_parts.append(raw)
            i += 1
            continue

        # ---- horizontal rule ---------------------------------------------------
        if re.match(r"^\s*([-*_])(?:\s*\1){2,}\s*$", line):
            close_list()
            out.append("<hr>")
            i += 1
            continue

        # ---- blockquote --------------------------------------------------------
        if stripped.startswith(">"):
            close_list()
            quote: list[str] = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append(f"<blockquote><p>{_inline(' '.join(quote))}</p></blockquote>")
            continue

        # ---- lists -------------------------------------------------------------
        item = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", line)
        if item:
            if not in_list:
                out.append("<ul>")
                in_list = True
            indent = len(item.group(1))
            out.append(f'<li class="depth-{min(indent // 2, 3)}">{_inline(item.group(3))}</li>')
            plain_parts.append(item.group(3))
            i += 1
            continue
        close_list()

        # ---- html passthrough --------------------------------------------------
        if stripped.startswith("<") and stripped.endswith(">"):
            out.append(stripped)
            i += 1
            continue

        # ---- blank -------------------------------------------------------------
        if not stripped:
            i += 1
            continue

        # ---- paragraph ---------------------------------------------------------
        paragraph = [stripped]
        i += 1
        while (
            i < n
            and lines[i].strip()
            and not lines[i].strip().startswith(("|", ">", "#", "```", "~~~"))
            and not re.match(r"^(\s*)([-*+]|\d+[.)])\s+", lines[i])
            and not re.match(r"^\s*([-*_])(?:\s*\1){2,}\s*$", lines[i])
        ):
            paragraph.append(lines[i].strip())
            i += 1
        text_joined = " ".join(paragraph)
        out.append(f"<p>{_inline(text_joined)}</p>")
        plain_parts.append(text_joined)

    close_list()
    return Rendered("\n".join(out), headings, " ".join(plain_parts))


# --------------------------------------------------------------------------- shell

CSS = """
:root {
  --bg: #f6f7fb; --surface: #ffffff; --surface-2: #eef1f7; --text: #131722;
  --muted: #5a6478; --subtle: #8b93a7; --border: #dfe3ec; --border-strong: #c3cad9;
  --brand: #3b5bdb; --brand-soft: #e7ecff; --accent: #0ca678; --warn: #f08c00; --danger: #e03131;
  --code-bg: #f2f4f9; --shadow: 0 1px 2px rgba(16,24,40,.06), 0 8px 24px rgba(16,24,40,.06);
  --radius: 12px; --sidebar: 292px; --header: 60px;
}
[data-theme="dark"] {
  --bg: #0b0e15; --surface: #131722; --surface-2: #1a1f2e; --text: #e6e9f0;
  --muted: #9aa3b8; --subtle: #6b7488; --border: #232a3b; --border-strong: #333c52;
  --brand: #748ffc; --brand-soft: #1b2447; --accent: #38d9a9; --warn: #ffc078; --danger: #ff8787;
  --code-bg: #161c29; --shadow: 0 1px 2px rgba(0,0,0,.4), 0 10px 30px rgba(0,0,0,.35);
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; scrollbar-gutter: stable; }
body {
  margin: 0; background: var(--bg); color: var(--text);
  font: 15px/1.7 -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
}
a { color: var(--brand); text-decoration: none; }
a:hover { text-decoration: underline; }
code {
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  font-size: .875em; background: var(--code-bg); padding: .15em .4em;
  border-radius: 5px; border: 1px solid var(--border);
}
pre.code {
  background: var(--code-bg); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 16px 18px; overflow-x: auto; margin: 18px 0; line-height: 1.6;
}
pre.code code { background: none; border: 0; padding: 0; font-size: 13px; }
pre.mermaid {
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 22px; margin: 22px 0; overflow-x: auto; text-align: center;
}
pre.mermaid[data-failed="true"] { text-align: left; }
table { border-collapse: collapse; width: 100%; margin: 18px 0; font-size: 14px; }
.table-scroll { overflow-x: auto; }
th, td { border: 1px solid var(--border); padding: 9px 12px; text-align: left; vertical-align: top; }
thead th { background: var(--surface-2); font-weight: 600; white-space: nowrap; }
tbody tr:nth-child(even) { background: color-mix(in srgb, var(--surface-2) 45%, transparent); }
img, .diagram-object { max-width: 100%; height: auto; border-radius: 10px; display: block; margin: 18px auto; }
.diagram-object { width: 100%; min-height: 240px; border: 1px solid var(--border); background: var(--surface); }
blockquote {
  margin: 18px 0; padding: 12px 18px; border-left: 4px solid var(--brand);
  background: var(--brand-soft); border-radius: 0 8px 8px 0;
}
blockquote p { margin: 0; }
hr { border: 0; border-top: 1px solid var(--border); margin: 32px 0; }
ul { padding-left: 22px; margin: 12px 0; }
li { margin: 5px 0; }
li.depth-1 { margin-left: 18px; } li.depth-2 { margin-left: 36px; } li.depth-3 { margin-left: 54px; }

/* ------------------------------------------------------------------ layout */
.topbar {
  position: sticky; top: 0; z-index: 40; height: var(--header);
  display: flex; align-items: center; gap: 14px; padding: 0 20px;
  background: color-mix(in srgb, var(--surface) 88%, transparent);
  backdrop-filter: saturate(180%) blur(12px); border-bottom: 1px solid var(--border);
}
.brand { display: flex; align-items: center; gap: 10px; font-weight: 700; letter-spacing: -.01em; }
.brand-mark {
  width: 30px; height: 30px; border-radius: 8px; display: grid; place-items: center;
  background: linear-gradient(135deg, var(--brand), var(--accent)); color: #fff; font-size: 14px;
}
.brand-text { font-size: 14px; line-height: 1.25; }
.brand-text small { display: block; font-weight: 500; font-size: 11px; color: var(--muted); }
.spacer { flex: 1; }
.search-wrap { position: relative; flex: 0 1 380px; }
.search-wrap input {
  width: 100%; height: 36px; padding: 0 34px 0 34px; border-radius: 9px;
  border: 1px solid var(--border); background: var(--surface-2); color: var(--text);
  font-size: 13.5px; outline: none;
}
.search-wrap input:focus { border-color: var(--brand); box-shadow: 0 0 0 3px var(--brand-soft); }
.search-wrap::before {
  content: "⌕"; position: absolute; left: 11px; top: 6px; color: var(--subtle); font-size: 16px;
}
.search-results {
  position: absolute; top: 42px; left: 0; right: 0; max-height: 60vh; overflow-y: auto;
  background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
  box-shadow: var(--shadow); display: none; z-index: 50;
}
.search-results[data-open="true"] { display: block; }
.search-results a { display: block; padding: 9px 13px; border-bottom: 1px solid var(--border); color: var(--text); }
.search-results a:last-child { border-bottom: 0; }
.search-results a:hover, .search-results a[data-active="true"] { background: var(--surface-2); }
.search-results small { display: block; color: var(--muted); font-size: 11.5px; }
.search-results mark { background: var(--brand-soft); color: var(--brand); border-radius: 3px; padding: 0 2px; }
.icon-btn {
  height: 34px; min-width: 34px; padding: 0 10px; border-radius: 9px; cursor: pointer;
  border: 1px solid var(--border); background: var(--surface-2); color: var(--text); font-size: 14px;
}
.icon-btn:hover { border-color: var(--border-strong); }
#menu-btn { display: none; }

.shell { display: grid; grid-template-columns: var(--sidebar) minmax(0, 1fr); align-items: start; }
.sidebar {
  position: sticky; top: var(--header); height: calc(100vh - var(--header));
  overflow-y: auto; padding: 18px 12px 60px; border-right: 1px solid var(--border);
  background: var(--surface); scrollbar-width: thin;
}
.nav-group-title {
  font-size: 11px; text-transform: uppercase; letter-spacing: .09em; font-weight: 700;
  color: var(--subtle); padding: 16px 10px 6px;
}
.sidebar a {
  display: block; padding: 7px 11px; border-radius: 8px; color: var(--muted);
  font-size: 13.5px; line-height: 1.35;
}
.sidebar a:hover { background: var(--surface-2); color: var(--text); text-decoration: none; }
.sidebar a.active { background: var(--brand-soft); color: var(--brand); font-weight: 600; }

.content { min-width: 0; padding: 30px 34px 90px; max-width: 1180px; }
.doc-head { margin-bottom: 26px; padding-bottom: 18px; border-bottom: 1px solid var(--border); }
.doc-head h1 { margin: 0 0 6px; font-size: 30px; letter-spacing: -.02em; }
.doc-head p { margin: 0; color: var(--muted); }
.toc {
  margin: 26px 0 8px; padding: 16px 20px; border: 1px solid var(--border);
  border-radius: var(--radius); background: var(--surface);
}
.toc summary { cursor: pointer; font-weight: 600; font-size: 13.5px; }
.toc ol { margin: 10px 0 0; padding-left: 20px; columns: 2; column-gap: 30px; font-size: 13.5px; }
.toc li { break-inside: avoid; }
.toc .lvl-3 { padding-left: 14px; color: var(--muted); font-size: 13px; }
.doc-body h2 { margin: 40px 0 12px; font-size: 22px; letter-spacing: -.015em; padding-bottom: 7px; border-bottom: 1px solid var(--border); }
.doc-body h3 { margin: 28px 0 10px; font-size: 17px; }
.doc-body h4 { margin: 20px 0 8px; font-size: 15px; color: var(--muted); }
.doc-body p { margin: 12px 0; }
.anchor-link { opacity: 0; margin-left: 8px; color: var(--subtle); font-weight: 400; }
h2:hover .anchor-link, h3:hover .anchor-link, h4:hover .anchor-link { opacity: 1; }
.doc-foot {
  margin-top: 46px; padding-top: 18px; border-top: 1px solid var(--border);
  display: flex; justify-content: space-between; gap: 14px; font-size: 13px; color: var(--muted);
  flex-wrap: wrap;
}
.backdrop { display: none; }

/* ------------------------------------------------------------------ landing */
.hero {
  border-radius: 18px; padding: 42px 40px; margin-bottom: 26px; color: #fff;
  background: linear-gradient(135deg, #1c2b6b 0%, #3b5bdb 48%, #0ca678 130%);
  box-shadow: var(--shadow);
}
.hero h1 { margin: 0 0 10px; font-size: 34px; line-height: 1.15; letter-spacing: -.03em; }
.hero p { margin: 0 0 18px; font-size: 16px; opacity: .93; max-width: 66ch; }
.hero .cta { display: flex; gap: 10px; flex-wrap: wrap; }
.hero .cta a {
  padding: 9px 17px; border-radius: 9px; font-weight: 600; font-size: 14px;
  background: rgba(255,255,255,.95); color: #16225c;
}
.hero .cta a.secondary { background: rgba(255,255,255,.16); color: #fff; border: 1px solid rgba(255,255,255,.4); }
.hero .cta a:hover { text-decoration: none; transform: translateY(-1px); }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(118px, 1fr)); gap: 12px; margin-bottom: 30px; }
.stat {
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 15px 16px;
}
.stat b { display: block; font-size: 24px; letter-spacing: -.02em; color: var(--brand); }
.stat span { font-size: 12px; color: var(--muted); }
.card {
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 22px 24px; margin-bottom: 22px;
}
.card > h2 { margin: 0 0 6px; border: 0; font-size: 19px; }
.card > p.lede { margin: 0 0 16px; color: var(--muted); font-size: 14px; }
.grid-2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(310px, 1fr)); gap: 16px; }
.steps { display: grid; grid-template-columns: repeat(auto-fit, minmax(268px, 1fr)); gap: 14px; }
.step {
  border: 1px solid var(--border); border-radius: var(--radius); padding: 16px 18px; background: var(--surface-2);
}
.step b { display: flex; align-items: center; gap: 9px; font-size: 14.5px; margin-bottom: 5px; }
.step .num {
  width: 22px; height: 22px; border-radius: 6px; display: grid; place-items: center; flex: none;
  background: var(--brand); color: #fff; font-size: 12px; font-weight: 700;
}
.step p { margin: 0; font-size: 13px; color: var(--muted); line-height: 1.55; }
.cmd {
  display: flex; align-items: center; gap: 10px; padding: 11px 14px; margin-bottom: 9px;
  background: var(--code-bg); border: 1px solid var(--border); border-radius: 9px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px;
}
.cmd code { background: none; border: 0; padding: 0; color: var(--accent); font-weight: 600; flex: none; }
.cmd small { color: var(--muted); font-family: inherit; font-size: 12px; }
.cmd .copy {
  margin-left: auto; border: 1px solid var(--border); background: var(--surface); color: var(--muted);
  border-radius: 6px; padding: 2px 9px; font-size: 11.5px; cursor: pointer; flex: none;
}
.cmd .copy:hover { color: var(--brand); border-color: var(--brand); }
.tag-row { display: flex; flex-wrap: wrap; gap: 7px; }
.tag {
  font-size: 12px; padding: 4px 10px; border-radius: 999px; background: var(--surface-2);
  border: 1px solid var(--border); color: var(--muted);
}
.doc-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(268px, 1fr)); gap: 13px; }
.doc-card {
  display: block; padding: 15px 17px; border: 1px solid var(--border); border-radius: var(--radius);
  background: var(--surface); color: var(--text);
}
.doc-card:hover { border-color: var(--brand); text-decoration: none; transform: translateY(-2px); box-shadow: var(--shadow); }
.doc-card b { display: block; font-size: 14px; margin-bottom: 3px; }
.doc-card small { color: var(--muted); font-size: 12.5px; line-height: 1.5; display: block; }
.notfound { text-align: center; padding: 80px 20px; }
.notfound h1 { font-size: 62px; margin: 0; color: var(--brand); letter-spacing: -.04em; }

/* ------------------------------------------------------------------ responsive */
@media (max-width: 1000px) {
  .shell { grid-template-columns: minmax(0, 1fr); }
  #menu-btn { display: inline-flex; }
  .sidebar {
    position: fixed; top: var(--header); left: 0; width: var(--sidebar); z-index: 35;
    transform: translateX(-100%); transition: transform .18s ease;
  }
  body[data-drawer="open"] .sidebar { transform: none; }
  body[data-drawer="open"] { overflow: hidden; }
  body[data-drawer="open"] .backdrop {
    display: block; position: fixed; inset: var(--header) 0 0 0; z-index: 30;
    background: rgba(0,0,0,.45);
  }
  .content { padding: 22px 18px 70px; }
  .toc ol { columns: 1; }
  .hero { padding: 30px 24px; }
  .hero h1 { font-size: 26px; }
  .brand-text small { display: none; }
}
@media (max-width: 560px) {
  .search-wrap { flex: 1 1 auto; }
  .brand-text { display: none; }
  th, td { font-size: 13px; padding: 7px 9px; }
}
@media (prefers-reduced-motion: reduce) { * { transition: none !important; scroll-behavior: auto !important; } }
@media print {
  .topbar, .sidebar, .toc, .backdrop { display: none !important; }
  .shell { grid-template-columns: 1fr; }
  .content { max-width: none; padding: 0; }
  pre.mermaid { border: 1px solid #ccc; }
}
"""

JS = """
(function () {
  'use strict';

  // ---------------------------------------------------------------- theme
  var KEY = 'pip-docs-theme';
  function systemTheme() {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  function applyTheme(t) {
    document.documentElement.setAttribute('data-theme', t);
    var btn = document.getElementById('theme-btn');
    if (btn) { btn.textContent = t === 'dark' ? '☀' : '☾'; btn.title = 'Switch to ' + (t === 'dark' ? 'light' : 'dark') + ' theme'; }
  }
  var stored = null;
  try { stored = localStorage.getItem(KEY); } catch (e) {}
  applyTheme(stored || systemTheme());
  var themeBtn = document.getElementById('theme-btn');
  if (themeBtn) {
    themeBtn.addEventListener('click', function () {
      var next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      try { localStorage.setItem(KEY, next); } catch (e) {}
      applyTheme(next);
    });
  }

  // ---------------------------------------------------------------- drawer
  var menuBtn = document.getElementById('menu-btn');
  if (menuBtn) {
    menuBtn.addEventListener('click', function () {
      var open = document.body.getAttribute('data-drawer') === 'open';
      document.body.setAttribute('data-drawer', open ? 'closed' : 'open');
    });
  }
  var backdrop = document.querySelector('.backdrop');
  if (backdrop) backdrop.addEventListener('click', function () { document.body.setAttribute('data-drawer', 'closed'); });

  // ---------------------------------------------------------------- search
  var input = document.getElementById('q');
  var results = document.getElementById('results');
  var index = null, cursor = -1;

  function loadIndex() {
    if (index) return Promise.resolve(index);
    return fetch('search-index.json').then(function (r) { return r.json(); }).then(function (d) { index = d; return index; });
  }

  function esc(s) { return s.replace(/[&<>"]/g, function (c) { return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]; }); }

  function highlight(text, q) {
    var i = text.toLowerCase().indexOf(q.toLowerCase());
    if (i < 0) return esc(text);
    return esc(text.slice(0, i)) + '<mark>' + esc(text.slice(i, i + q.length)) + '</mark>' + esc(text.slice(i + q.length));
  }

  function run(q) {
    if (!results) return;
    q = q.trim();
    if (q.length < 2) { results.setAttribute('data-open', 'false'); results.innerHTML = ''; cursor = -1; return; }
    loadIndex().then(function (idx) {
      var terms = q.toLowerCase().split(/\\s+/);
      var hits = [];
      for (var i = 0; i < idx.length; i++) {
        var doc = idx[i];
        var hay = (doc.title + ' ' + doc.text).toLowerCase();
        var score = 0, ok = true;
        for (var t = 0; t < terms.length; t++) {
          var n = hay.split(terms[t]).length - 1;
          if (!n) { ok = false; break; }
          score += n * (doc.title.toLowerCase().indexOf(terms[t]) >= 0 ? 3 : 1);
        }
        if (ok) hits.push({ doc: doc, score: score, where: bestWhere(doc, terms[0]) });
      }
      hits.sort(function (a, b) { return b.score - a.score; });
      hits = hits.slice(0, 14);
      if (!hits.length) {
        results.innerHTML = '<a data-nohref="1"><small>No matches for "' + esc(q) + '"</small></a>';
      } else {
        results.innerHTML = hits.map(function (h, i) {
          return '<a href="' + h.doc.url + '" data-i="' + i + '"><b>' + highlight(h.doc.title, terms[0]) +
                 '</b><small>' + esc(h.doc.nav) + ' — ' + esc(h.where) + '</small></a>';
        }).join('');
      }
      cursor = -1;
      results.setAttribute('data-open', 'true');
    });
  }

  function bestWhere(doc, term) {
    var t = term.toLowerCase();
    var idx = doc.text.toLowerCase().indexOf(t);
    if (idx < 0) return doc.summary || '';
    var start = Math.max(0, idx - 55);
    var snippet = doc.text.slice(start, start + 150);
    return (start > 0 ? '…' : '') + snippet.trim() + '…';
  }

  function move(delta) {
    var links = results.querySelectorAll('a[href]');
    if (!links.length) return;
    if (cursor >= 0 && links[cursor]) links[cursor].removeAttribute('data-active');
    cursor = (cursor + delta + links.length) % links.length;
    links[cursor].setAttribute('data-active', 'true');
    links[cursor].scrollIntoView({ block: 'nearest' });
  }

  if (input) {
    input.addEventListener('input', function () { run(input.value); });
    input.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown') { e.preventDefault(); move(1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); move(-1); }
      else if (e.key === 'Enter') {
        var active = results.querySelector('a[data-active="true"]') || results.querySelector('a[href]');
        if (active) { e.preventDefault(); window.location.href = active.getAttribute('href'); }
      } else if (e.key === 'Escape') { input.value = ''; results.setAttribute('data-open', 'false'); input.blur(); }
    });
    document.addEventListener('click', function (e) {
      if (!results.contains(e.target) && e.target !== input) results.setAttribute('data-open', 'false');
    });
    document.addEventListener('keydown', function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); input.focus(); input.select(); }
      if (e.key === '/' && document.activeElement !== input && !/^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName)) {
        e.preventDefault(); input.focus();
      }
    });
  }

  // ---------------------------------------------------------------- diagrams
  var blocks = document.querySelectorAll('pre.mermaid');
  if (blocks.length) {
    var local = false;
    import('./' + MERMAID_LOCAL).then(function (m) {
      local = true; start(m.default, blocks);
    }).catch(function () {
      import(MERMAID_CDN).then(function (m) { start(m.default, blocks); })
        .catch(function () { blocks.forEach(function (b) { b.setAttribute('data-failed', 'true'); }); });
    });
  }
  function start(mermaid, blocks) {
    mermaid.initialize({
      startOnLoad: false, securityLevel: 'strict', theme: 'base', fontFamily: 'Inter, system-ui, sans-serif',
      flowchart: { curve: 'basis', useMaxWidth: true }, sequence: { useMaxWidth: true }
    });
    var theme = document.documentElement.getAttribute('data-theme');
    mermaid.render('m' + Math.random().toString(36).slice(2), '', '').catch(function () {});
    blocks.forEach(function (block, i) {
      var id = 'mmd-' + i;
      block.removeAttribute('data-failed');
      mermaid.render(id, block.textContent).then(function (r) {
        var holder = document.createElement('div');
        holder.className = 'diagram';
        holder.innerHTML = r.svg;
        block.parentNode.replaceChild(holder, block);
      }).catch(function () { block.setAttribute('data-failed', 'true'); });
    });
    void theme; void local;
  }

  // ---------------------------------------------------------------- toc + scrollspy
  var links = Array.prototype.slice.call(document.querySelectorAll('.toc a'));
  if (links.length) {
    var targets = links.map(function (a) { return document.getElementById(a.getAttribute('href').slice(1)); }).filter(Boolean);
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        links.forEach(function (a) {
          a.style.color = a.getAttribute('href') === '#' + entry.target.id ? 'var(--brand)' : '';
          a.style.fontWeight = a.getAttribute('href') === '#' + entry.target.id ? '600' : '';
        });
      });
    }, { rootMargin: '-70px 0px -75% 0px' });
    targets.forEach(function (t) { observer.observe(t); });
  }

  // ---------------------------------------------------------------- copy buttons
  document.querySelectorAll('.cmd').forEach(function (row) {
    var btn = row.querySelector('.copy');
    if (!btn) return;
    btn.addEventListener('click', function () {
      var text = row.querySelector('code').textContent;
      var done = function () { btn.textContent = 'copied'; setTimeout(function () { btn.textContent = 'copy'; }, 1400); };
      if (navigator.clipboard) navigator.clipboard.writeText(text).then(done, function () {});
      else done();
    });
  });
})();
"""

MERMAID_LOCAL_PATH = "vendor/mermaid.esm.min.mjs"


def page(
    *,
    title: str,
    body: str,
    active: str,
    description: str = "",
    extra_head: str = "",
) -> str:
    """Wrap rendered body content in the shared site shell."""
    nav_html = []
    for group, files in NAV_GROUPS:
        nav_html.append(f'<div class="nav-group-title">{html.escape(group)}</div>')
        for fname in files:
            slug = fname[:-3].lower()
            cls = ' class="active"' if fname == active else ""
            label, blurb = next(((t, b) for f, t, b in NAV if f == fname), (fname, ""))
            nav_html.append(
                f'<a href="{slug}.html"{cls} title="{html.escape(blurb)}">{html.escape(label)}</a>'
            )

    full_title = f"{title} — {TITLE}" if title else TITLE
    return f"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{html.escape(description or SUBTITLE)}">
<meta name="color-scheme" content="light dark">
<meta property="og:type" content="website">
<meta property="og:title" content="{html.escape(full_title)}">
<meta property="og:description" content="{html.escape(description or SUBTITLE)}">
<title>{html.escape(full_title)}</title>
<link rel="stylesheet" href="assets/site.css">
<link rel="icon" href="assets/favicon.svg" type="image/svg+xml">
{extra_head}
</head>
<body>
<header class="topbar">
  <button class="icon-btn" id="menu-btn" aria-label="Toggle navigation">☰</button>
  <a class="brand" href="index.html">
    <span class="brand-mark">W</span>
    <span class="brand-text">Web-to-Warehouse<small>Product Intelligence Pipeline v{SITE_VERSION}</small></span>
  </a>
  <span class="spacer"></span>
  <div class="search-wrap">
    <input id="q" type="search" placeholder="Search the documentation…  (Ctrl-K)" autocomplete="off"
           aria-label="Search documentation" spellcheck="false">
    <div class="search-results" id="results" data-open="false"></div>
  </div>
  <button class="icon-btn" id="theme-btn" aria-label="Toggle colour theme">☾</button>
</header>
<div class="shell">
  <nav class="sidebar" aria-label="Documentation">
{chr(10).join(nav_html)}
  </nav>
  <main class="content">
{body}
  </main>
</div>
<div class="backdrop"></div>
<script type="module">
  const MERMAID_LOCAL = {json.dumps(MERMAID_LOCAL)};
  const MERMAID_CDN = {json.dumps(MERMAID_CDN)};
</script>
<script type="module" src="assets/site.js"></script>
</body>
</html>
"""


def doc_page(fname: str, title: str, blurb: str) -> tuple[str, dict]:
    """Render one Markdown document into a full page plus its search entry."""
    path = DOCS / fname
    text = path.read_text(encoding="utf-8")

    # The very first heading is the page title; drop it to avoid a duplicate <h1>.
    lines = text.split("\n")
    if lines and lines[0].startswith("# "):
        text = "\n".join(lines[1:])

    rendered = render_markdown(text)

    toc_items = [
        f'<li class="lvl-{lvl}"><a href="#{anchor}">{html.escape(raw)}</a></li>'
        for lvl, raw, anchor in rendered.headings
        if 2 <= lvl <= 3
    ]
    toc = (
        '<details class="toc"' + ("" if len(toc_items) > 14 else " open") + ">"
        "<summary>On this page</summary><ol>" + "".join(toc_items) + "</ol></details>"
        if toc_items
        else ""
    )

    prev_doc = next((f for f, _, _ in NAV if NAV[NAV.index((fname, title, blurb)) - 1][0] == f), None)
    order = [f for f, _, _ in NAV]
    idx = order.index(fname)
    prev_link = f'<a href="{order[idx - 1][:-3].lower()}.html">← {NAV[idx - 1][1]}</a>' if idx > 0 else ""
    next_link = (
        f'<a href="{order[idx + 1][:-3].lower()}.html">{NAV[idx + 1][1]} →</a>'
        if idx < len(order) - 1
        else ""
    )

    body = f"""    <div class="doc-head">
      <h1>{html.escape(title)}</h1>
      <p>{html.escape(blurb)}</p>
    </div>
    {toc}
    <article class="doc-body">
{rendered.body}
    </article>
    <div class="doc-foot">
      <span>{prev_link}</span>
      <span><a href="../README.md">Source markdown</a></span>
      <span>{next_link}</span>
    </div>"""

    entry = {
        "url": f"{fname[:-3].lower()}.html",
        "title": title,
        "nav": blurb,
        "summary": blurb,
        "text": rendered.plain[:6000],
    }
    del prev_doc
    return page(title=title, body=body, active=fname, description=blurb), entry


def landing_page() -> str:
    """The site home page: what this is, how to run it, and where to read next."""
    stats = "".join(
        f'<div class="stat"><b>{v}</b><span>{html.escape(label)}</span></div>' for v, label in STATS
    )
    steps = "".join(
        f'<div class="step"><b><span class="num">{i}</span>{html.escape(n)}</b><p>{html.escape(d)}</p></div>'
        for i, (n, d) in enumerate(PIPELINE_STEPS, 1)
    )
    cmds = "".join(
        f'<div class="cmd"><code>{html.escape(c)}</code><small>{html.escape(w)}</small>'
        f'<button class="copy" type="button">copy</button></div>'
        for w, c, _ in QUICKSTART
    )
    tags = "".join(f'<span class="tag">{html.escape(t)}</span>' for t in TOPICS)
    cards = "".join(
        f'<a class="doc-card" href="{f[:-3].lower()}.html"><b>{html.escape(t)}</b>'
        f"<small>{html.escape(b)}</small></a>"
        for f, t, b in NAV
        if f != "README.md"
    )

    body = f"""    <section class="hero">
      <h1>{html.escape(TITLE)}</h1>
      <p>{html.escape(SUBTITLE)}. A DEPI data-engineering graduation project: a compliance-first
      crawler feeds a Kimball star schema on PostgreSQL and MySQL, twelve data-quality rules score
      every load, and 113 REST operations with a React dashboard make the result explorable.</p>
      <div class="cta">
        <a href="{QUICKSTART[0][1].split()[0] and "03_roles_and_responsibilities.html"}">Read the documentation</a>
        <a class="secondary" href="14_api_documentation.html">API reference</a>
        <a class="secondary" href="21_architecture_deep_dive.html">Architecture</a>
      </div>
    </section>

    <div class="stats">{stats}</div>

    <section class="card">
      <h2>What it does</h2>
      <p class="lede">Six phases, each one measured and reversible.</p>
      <div class="steps">{steps}</div>
    </section>

    <section class="card">
      <h2>Run it</h2>
      <p class="lede">Six commands from a clean checkout to a populated dashboard.</p>
      {cmds}
    </section>

    <section class="card">
      <h2>Technology</h2>
      <p class="lede">Everything below runs from <code>make install &amp;&amp; make up</code>.</p>
      <div class="tag-row">{tags}</div>
    </section>

    <section class="card">
      <h2>Documentation</h2>
      <p class="lede">{len(NAV) - 1} documents covering proposal, design, build, operation and evaluation.</p>
      <div class="doc-cards">{cards}</div>
    </section>"""
    return page(title="", body=body, active="", description=SUBTITLE)


TOPICS = [
    "Python 3.12",
    "FastAPI",
    "SQLAlchemy 2.0",
    "Pydantic",
    "httpx",
    "BeautifulSoup",
    "Apache Airflow 2.10",
    "PostgreSQL 16",
    "MySQL 8.4",
    "React 19",
    "TypeScript",
    "Vite",
    "Tailwind CSS",
    "TanStack Query",
    "Recharts",
    "Docker Compose",
    "Nginx",
    "Typer CLI",
    "structlog",
    "pytest",
    "mypy",
    "ruff",
    "ESLint",
    "Mermaid",
]

FAVICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="#3b5bdb"/><stop offset="1" stop-color="#0ca678"/>
</linearGradient></defs>
<rect width="32" height="32" rx="8" fill="url(#g)"/>
<path d="M9 11h14M9 16h14M9 21h9" stroke="#fff" stroke-width="2.4" stroke-linecap="round"/>
</svg>"""


def build(out_dir: Path) -> list[Path]:
    """Generate every page, the search index and the static assets."""
    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "assets").mkdir(parents=True)
    (out_dir / "vendor").mkdir(parents=True)

    written: list[Path] = []

    index = []
    for fname, title, blurb in NAV:
        source = DOCS / fname
        if not source.exists():
            print(f"  ! skipped {fname} (not found)")
            continue
        content, entry = doc_page(fname, title, blurb)
        target = out_dir / f"{fname[:-3].lower()}.html"
        target.write_text(content, encoding="utf-8")
        written.append(target)
        index.append(entry)

    (out_dir / "index.html").write_text(landing_page(), encoding="utf-8")
    written.append(out_dir / "index.html")

    (out_dir / "404.html").write_text(
        page(
            title="Page not found",
            description="The requested documentation page does not exist.",
            active="",
            body="""    <div class="notfound">
      <h1>404</h1>
      <p>That page is not part of this documentation set.</p>
      <p><a href="index.html">Return to the overview</a></p>
    </div>""",
        ),
        encoding="utf-8",
    )
    written.append(out_dir / "404.html")

    (out_dir / "search-index.json").write_text(json.dumps(index, indent=0), encoding="utf-8")
    (out_dir / "assets" / "site.css").write_text(CSS, encoding="utf-8")
    (out_dir / "assets" / "site.js").write_text(JS, encoding="utf-8")
    (out_dir / "assets" / "favicon.svg").write_text(FAVICON, encoding="utf-8")

    # A local Mermaid build makes the site work fully offline; otherwise the CDN is used.
    local = _find_local_mermaid()
    if local:
        shutil.copy(local, out_dir / MERMAID_LOCAL_PATH)
        print(f"  + vendored mermaid runtime ({local.stat().st_size // 1024} KiB)")

    print(f"  + search index with {len(index)} documents")
    return written


def _find_local_mermaid() -> Path | None:
    for candidate in (
        ROOT / "frontend" / "node_modules" / "mermaid" / "dist" / "mermaid.esm.min.mjs",
        ROOT / "node_modules" / "mermaid" / "dist" / "mermaid.esm.min.mjs",
    ):
        if candidate.is_file():
            return candidate
    return None


def serve(out_dir: Path, port: int) -> None:
    """Serve the built site and open it in a browser."""
    handler = lambda *a, **kw: SimpleHTTPRequestHandler(*a, directory=str(out_dir), **kw)  # noqa: E731
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://localhost:{port}/"
    print(f"Serving {out_dir} at {url}  (Ctrl-C to stop)")
    with contextlib.suppress(Exception):
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the documentation website.")
    parser.add_argument("--out", default="site", help="output directory (default: site)")
    parser.add_argument("--serve", action="store_true", help="serve the result after building")
    parser.add_argument("--port", type=int, default=8001, help="port for --serve (default: 8001)")
    args = parser.parse_args()

    out_dir = (ROOT / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    print(f"Building documentation site into {out_dir}")
    written = build(out_dir)
    print(f"Done — {len(written)} pages.")
    if args.serve:
        serve(out_dir, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
