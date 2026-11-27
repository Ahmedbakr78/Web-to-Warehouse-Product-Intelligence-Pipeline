#!/usr/bin/env bash
#
# github_polish.sh — finalise the GitHub repository (About, topics, website,
# visibility option, release + downloadable assets). Safe & idempotent.
#
#   gh auth login                 # once, in your own terminal
#   ./scripts/github_polish.sh    # then this script
#
# Nothing here deletes any file, branch, tag, release, or issue.
#
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.."

REPO="${GH_REPO:-Ahmedbakr78/Web-to-Warehouse-Product-Intelligence-Pipeline}"
VERSION="$(cat VERSION 2>/dev/null || echo 1.14.0)"

if ! gh auth status >/dev/null 2>&1; then
  echo "GitHub CLI is not authenticated. Run 'gh auth login' first, then re-run this script." >&2
  exit 1
fi

echo "==> Repository: $REPO"

if [[ "${MAKE_PRIVATE:-false}" == "true" ]]; then
  echo "==> 1/6 Making the repository private"
  gh repo edit "$REPO" \
    --visibility private \
    --accept-visibility-change-consequences
else
  CURRENT_VIS=$(gh repo view "$REPO" --json visibility -q .visibility 2>/dev/null || echo "PUBLIC")
  echo "==> 1/6 Preserving repository visibility: $CURRENT_VIS (pass MAKE_PRIVATE=true to make private)"
fi

echo "==> 2/6 About: description (<= 350 chars)"
gh repo edit "$REPO" --description \
  "DEPI Data Engineering Capstone: Compliance-first Web-to-Warehouse Product Intelligence — 34 sources, 29-step cleaner, 4-signal dedupe, 29-table PostgreSQL & MySQL warehouse (23 views), 12 DQ rules, Airflow 2.10, FastAPI (24 routers, 222 ops), React 19 (23 screens, 767 features), 128 diagrams, 636 tests. AGPL-3.0."

echo "==> 3/6 About: website (GitHub Pages showcase + 39-doc portal)"
PAGES_URL="https://ahmedbakr78.github.io/Web-to-Warehouse-Product-Intelligence-Pipeline/"
gh repo edit "$REPO" --homepage "$PAGES_URL"

echo "==> 4/6 About: topics (20 top-tier keywords)"
gh repo edit "$REPO" \
  --add-topic data-engineering \
  --add-topic web-scraping \
  --add-topic beautifulsoup \
  --add-topic scrapy \
  --add-topic etl \
  --add-topic airflow \
  --add-topic postgresql \
  --add-topic mysql \
  --add-topic fastapi \
  --add-topic react \
  --add-topic data-quality \
  --add-topic data-warehouse \
  --add-topic deduplication \
  --add-topic price-tracking \
  --add-topic depi \
  --add-topic kimball \
  --add-topic docker \
  --add-topic rest-api \
  --add-topic data-pipeline \
  --add-topic data-visualization 2>/dev/null || true

echo "==> 5/6 Release v$VERSION"
if gh release view "v$VERSION" >/dev/null 2>&1; then
  echo "    release v$VERSION already exists - updating assets only"
else
  notes="$(mktemp)"
  cat > "$notes" <<EOF
# v$VERSION — DEPI Data Engineering Capstone Release

Production-ready, compliance-first **Web-to-Warehouse Product Intelligence Pipeline** with live **PostgreSQL 16 + MySQL 8.4** dual-warehouse parity, **Apache Airflow 2.10.5** orchestration, **FastAPI** (`24` routers, `222` operations), **React 19** (`23` screens, Light/Dark/System themes, mobile PWA), and automated **GitHub Pages** docs portal.

## Measured Scale & Quality (`v$VERSION`)
| Metric | Value |
| --- | --- |
| Registered Sources | **34** (`20` auto-selected real permitted APIs + BeautifulSoup/Scrapy adapters) |
| Kimball Warehouse | **29** physical tables · **23** analytical views (`PostgreSQL 16` & `MySQL 8.4`) |
| Data Quality Engine | **12** enforced rules across **6** dimensions |
| REST API Surface | **24** routers · **222** operations · JWT, 2FA TOTP, RBAC, Webhooks, SSE |
| Feature Catalogue | **767** catalogued UI/API features · **612** documented F-IDs |
| Documentation & Diagrams | **39** Markdown docs · **128** Mermaid diagrams (SVG + high-DPI PNG in PDF) |
| Verification | **636** backend pytest cases · **67** Vitest tests · **104/104** API smoke checks · **6/6** CI jobs |

## Included Deliverables
- **Consolidated PDF Documentation (`283+` pages, high-DPI diagrams)** (`Project_Documentation.pdf` & `Web-to-Warehouse-Product-Intelligence-Pipeline_Documentation.pdf`)
- **Executive Defence Deck (`12` slides)** (`deck.pdf`)
- **Pipeline Architecture Infographic** (`infographic.pdf` & `infographic.png`)
- **Live Website & Docs Portal:** $PAGES_URL

See [CHANGELOG.md](CHANGELOG.md) for the complete version history.
EOF
  git tag -a "v$VERSION" -m "v$VERSION — DEPI Data Engineering Capstone release" 2>/dev/null || true
  git push origin "v$VERSION" 2>/dev/null || true
  gh release create "v$VERSION" --title "v$VERSION — Full DEPI Capstone, Live Pages & 128-Diagram Suite" --notes-file "$notes"
  rm -f "$notes"
fi

for asset in \
  "Web-to-Warehouse-Product-Intelligence-Pipeline_Documentation.pdf" \
  "docs/assets/Project_Documentation.pdf" \
  "docs/assets/deck.pdf" \
  "docs/assets/infographic.pdf" \
  "docs/assets/infographic.png"; do
  if [[ -f "$asset" ]]; then
    gh release upload "v$VERSION" "$asset" --clobber >/dev/null && echo "    uploaded asset: $asset"
  fi
done

echo "==> 6/6 Verify"
gh repo view "$REPO" --json visibility,description,homepageUrl,repositoryTopics
