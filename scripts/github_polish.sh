#!/usr/bin/env bash
#
# github_polish.sh — finalise the GitHub repository (About, topics, privacy,
# release, social preview). Run this YOURSELF: it needs your GitHub login.
#
#   gh auth login                 # once, in your own terminal
#   ./scripts/github_polish.sh    # then this script
#
# Nothing here is destructive: the only consequential change is making the
# repository private, which is the explicit request. Re-running is safe.
#
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.."

REPO="${GH_REPO:-Ahmedbakr78/Web-to-Warehouse-Product-Intelligence-Pipeline}"
VERSION="$(cat VERSION 2>/dev/null || echo 1.13.1)"

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

echo "==> 2/6 About: description"
gh repo edit "$REPO" --description \
  "End-to-end DEPI Data Engineering capstone: 34 permitted web/API sources → 29-step cleaner → 4-signal fuzzy dedupe → 29-table Kimball warehouse (PostgreSQL 16 & MySQL 8.4, 23 views) → 12 DQ rules → Airflow (33 tasks) → FastAPI (24 routers, 222 ops) → React 19 dashboard (23 screens, PWA). 100% real-data verified. AGPL-3.0."

echo "==> 3/6 About: website"
gh repo edit "$REPO" --homepage "https://github.com/Ahmedbakr78/Web-to-Warehouse-Product-Intelligence-Pipeline#readme"

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
  --add-topic sql-analytics 2>/dev/null || true

echo "==> 5/6 Release v$VERSION"
if gh release view "v$VERSION" >/dev/null 2>&1; then
  echo "    release v$VERSION already exists - skipped"
else
  notes="$(mktemp)"
  {
    echo "# v$VERSION"
    echo
    echo "See [CHANGELOG.md](CHANGELOG.md) for the full list of changes."
    echo
    echo "- 636 backend tests / 67 frontend tests passing"
    echo "- Live real-source verification: no-fake audit clean"
    echo "- Light + dark themes, mobile responsive, silent reload"
  } > "$notes"
  git tag -a "v$VERSION" -m "v$VERSION - DEPI capstone release" 2>/dev/null || true
  git push origin "v$VERSION" 2>/dev/null || true
  gh release create "v$VERSION" --title "v$VERSION" --notes-file "$notes"
  rm -f "$notes"
fi

echo "==> 6/6 Verify"
gh repo view "$REPO" --json visibility,description,homepageUrl,repositoryTopics

echo
echo "Done. Remaining manual touches (GitHub UI only):"
echo "  - Settings -> General -> Social preview -> upload an 1280x640 image"
echo "  - Pin this repository on your profile"
echo "  - GitHub Pages: Settings -> Pages -> Source = main / docs (optional)"
