#!/usr/bin/env python3
"""Check internal links and heading anchors in a built documentation site.

``scripts/build_site.py`` produces plain HTML, so nothing verifies that the
result is navigable. This walks every generated page and reports:

* links to pages that were not generated,
* links to anchors that no heading defines,
* image references that point at a missing file,
* stray control characters left over from Markdown conversion.

External ``http(s)`` links are not fetched -- that would make CI slow and
flaky, and a link checker is not a crawler.

Usage::

    python3 scripts/check_links.py site
    python3 scripts/check_links.py /tmp/site --verbose
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

#: Attributes that carry a URL worth checking.
URL_ATTRS = re.compile(r'(?:href|src|data)="([^"]+)"')

#: Schemes and prefixes that are not internal references.
EXTERNAL = (
    "http://",
    "https://",
    "mailto:",
    "tel:",
    "data:",
    "javascript:",
    "//",
)


def load_pages(root: Path) -> dict[str, str]:
    """Map filename -> HTML text for every generated page."""
    return {path.name: path.read_text(encoding="utf-8") for path in sorted(root.glob("*.html"))}


def anchors(html: str) -> set[str]:
    """Every ``id`` a page defines."""
    return set(re.findall(r'\bid="([^"]+)"', html))


def check(root: Path, *, verbose: bool = False) -> int:
    pages = load_pages(root)
    if not pages:
        print(f"error: no HTML pages found in {root}", file=sys.stderr)
        return 2

    ids = {name: anchors(text) for name, text in pages.items()}
    assets = {p.name for p in root.rglob("*") if p.is_file()}

    problems: dict[str, list[str]] = defaultdict(list)
    checked = 0

    for name, text in pages.items():
        # A control character surviving conversion means an escaping bug upstream.
        for char in text:
            if ord(char) < 32 and char not in "\t\n\r":
                problems[name].append(f"stray control character U+{ord(char):04X}")
                break

        for url in URL_ATTRS.findall(text):
            if url.startswith(EXTERNAL) or url.startswith("#") is False and url.startswith(".."):
                continue
            if url.startswith("#"):
                if url[1:] and url[1:] not in ids[name]:
                    problems[name].append(f"anchor not found on this page: {url}")
                continue

            path, _, fragment = url.partition("#")
            if not path:
                continue

            if path.startswith(("assets/", "vendor/")):
                if Path(path).name not in assets:
                    problems[name].append(f"missing asset: {path}")
                continue

            # A link that climbs out of the built tree points at source markdown,
            # which is intentional for the "source markdown" footer link.
            if path.startswith(".."):
                continue

            checked += 1
            if path not in pages:
                problems[name].append(f"link to a page that was not generated: {path}")
                continue
            if fragment and fragment not in ids[path]:
                problems[name].append(f"anchor {url} does not exist on {path}")

    total = sum(len(v) for v in problems.values())

    if total == 0:
        print(f"Checked {checked} internal links across {len(pages)} pages — all resolve.")
        return 0

    for name in sorted(problems):
        print(f"\n{name}")
        for issue in problems[name]:
            print(f"  - {issue}")
            if verbose:
                print(f"    {problems[name][0]}")

    print(f"\n{total} problem(s) found across {len(problems)} page(s).")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("site", nargs="?", default="site", help="built site directory")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    root = Path(args.site)
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2

    return check(root, verbose=args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())