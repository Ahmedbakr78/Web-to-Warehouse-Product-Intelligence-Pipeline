#!/usr/bin/env python3
"""Regression test: ``build_site.slugify`` must match GitHub's ``github-slugger``.

The documentation links to its own headings with hand-written anchors. If our
slug algorithm ever drifts from GitHub's, every one of those in-page links breaks
silently -- the page still loads, the anchor simply does not exist.

The cases below were produced by the ``github-slugger`` package that GitHub uses
itself, so they are the specification rather than a guess. Regenerate with::

    npm install github-slugger
    node -e "import('github-slugger').then(({default:S})=>{const s=new S();\\
      for (const c of CASES) console.log(JSON.stringify([c, s.slug(c)]))})"

Run standalone (``python3 scripts/check_slugify.py``) or under pytest.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_builder():
    """Import ``build_site`` without triggering the package's ``__main__``."""
    spec = importlib.util.spec_from_file_location("_build_site", ROOT / "scripts" / "build_site.py")
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError("cannot load scripts/build_site.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


#: (heading text, expected slug) pairs captured from github-slugger.
CASES: list[tuple[str, str]] = [
    ("Purpose", "purpose"),
    ("Table of contents", "table-of-contents"),
    # An em-dash between spaces leaves a double hyphen. This is the case that a
    # naive "collapse hyphens" fix breaks.
    ("1. Sequence diagram — one pipeline run", "1-sequence-diagram--one-pipeline-run"),
    ("Theme 1 — dimensional modelling", "theme-1--dimensional-modelling"),
    ("API / REST endpoints", "api--rest-endpoints"),
    # Whitespace becomes one hyphen per character, never collapsed.
    ("Multiple   spaces", "multiple---spaces"),
    ("  spaced  ", "--spaced--"),
    # Parentheses and dots are dropped without merging the hyphens they sat between.
    ("4. Warehouse model (20)", "4-warehouse-model-20"),
    ("Version 1.3.0 release", "version-130-release"),
    ("Trailing punctuation...", "trailing-punctuation"),
    # Underscores are word characters and survive.
    ("key_underscore and dash", "key_underscore-and-dash"),
    # Slashes and quotes leave gaps.
    ('A/B testing & "quotes"', "ab-testing--quotes"),
    ("a—b", "ab"),
    # Hyphens are preserved verbatim, including leading and trailing.
    ("--dashes--", "--dashes--"),
    ("-x", "-x"),
    ("x-", "x-"),
    ("— leading em-dash", "-leading-em-dash"),
    # Case is lowered, contractions and percent signs handled.
    ("CamelCaseHeading", "camelcaseheading"),
    ("It's here", "its-here"),
    ("100% coverage", "100-coverage"),
    ("!!!bang!!!", "bang"),
    # Non-ASCII is preserved, not transliterated.
    ("Ünïcödé hèading", "ünïcödé-hèading"),
    ("中文标题", "中文标题"),
]


def test_slugify_matches_github_slugger() -> None:
    slugify = _load_builder().slugify
    mismatches = [
        (text, expected, slugify(text)) for text, expected in CASES if slugify(text) != expected
    ]
    assert not mismatches, "slugify diverges from github-slugger:\n" + json.dumps(
        [{"input": t, "github": g, "ours": o} for t, g, o in mismatches],
        ensure_ascii=False,
        indent=2,
    )


def test_real_document_headings_resolve() -> None:
    """Every in-page anchor written by hand in the docs must exist on that page."""
    import re

    builder = _load_builder()
    broken: list[str] = []

    for source in [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]:
        text = source.read_text(encoding="utf-8")

        anchors: dict[str, int] = {}
        for _level, raw in re.findall(r"^(#{1,6})\s+(.*)$", text, re.M):
            base = builder.slugify(re.sub(r"[#*`]", "", raw).strip())
            anchors[base] = anchors.get(base, 0) + 1

        for target in re.findall(r"\]\(#([^)]+)\)", text):
            if target not in anchors:
                broken.append(f"{source.relative_to(ROOT)} -> #{target}")

    assert not broken, "broken in-page anchors:\n  " + "\n  ".join(broken)


if __name__ == "__main__":
    try:
        test_slugify_matches_github_slugger()
        test_real_document_headings_resolve()
    except AssertionError as exc:
        print(f"FAIL\n{exc}", file=sys.stderr)
        raise SystemExit(1) from None
    print(f"OK — {len(CASES)} slug cases match github-slugger; document anchors resolve.")
