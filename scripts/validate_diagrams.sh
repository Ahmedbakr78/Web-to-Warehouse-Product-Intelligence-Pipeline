#!/usr/bin/env bash
# Validate that every Mermaid diagram in the repository actually parses.
#
# GitHub renders Mermaid at render time, which means a syntax error in a diagram shows up as a
# broken box on the README rather than as a failed build. This script catches that before review.
#
# Requires the Mermaid CLI:
#
#     npm install -g @mermaid-js/mermaid-cli
#
# Usage:
#
#     bash scripts/validate_diagrams.sh              # parse-check every diagram
#     bash scripts/validate_diagrams.sh --render     # also write SVGs to docs/diagrams/out
#
# Exit code 0 means every diagram parsed.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/docs/diagrams/out"
TMP="$(mktemp -d)"
RENDER=0
[[ "${1:-}" == "--render" ]] && RENDER=1

trap 'rm -rf "$TMP"' EXIT

if ! command -v mmdc >/dev/null 2>&1; then
  cat >&2 <<'EOF'
error: mmdc not found.

Install the Mermaid CLI first:

    npm install -g @mermaid-js/mermaid-cli

Or skip this check locally — CI runs it as part of the documentation job.
EOF
  exit 127
fi

# ---------------------------------------------------------------- extract
echo "Extracting Mermaid blocks from README.md and docs/*.md ..."
"$ROOT/.venv/bin/python" - "$TMP" "$ROOT" <<'PY'
import pathlib, re, sys

tmp, root = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
sources = [root / "README.md", *sorted((root / "docs").glob("*.md"))]

index, total = [], 0
for source in sources:
    text = source.read_text(encoding="utf-8")
    rel = source.relative_to(root)
    for position, block in enumerate(re.findall(r"```mermaid\n(.*?)```", text, re.S), 1):
        path = tmp / f"{total:03d}.mmd"
        path.write_text(block, encoding="utf-8")
        first = block.strip().split("\n")[0][:60]
        index.append((total, str(rel), position, first))
        total += 1

if total == 0:
    print("no Mermaid diagrams found", file=sys.stderr)
    raise SystemExit(1)

with (tmp / "index.tsv").open("w", encoding="utf-8") as handle:
    for number, source, position, first in index:
        handle.write(f"{number}\t{source}\t{position}\t{first}\n")

print(f"  found {total} diagrams")
PY

TOTAL=$(wc -l < "$TMP/index.tsv")
OK=0
FAILED=0

# Puppeteer needs these flags inside containers and CI runners.
PUPPETEER_JSON="$TMP/puppeteer.json"
cat > "$PUPPETEER_JSON" <<'EOF'
{"args": ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
EOF

mkdir -p "$OUT"

while IFS=$'\t' read -r number source position first; do
  target="$TMP/$number.svg"
  if [[ $RENDER -eq 1 ]]; then
    destination="$OUT/$(basename "${source%.md}")-$number.svg"
  else
    destination="$target"
  fi

  if error=$(mmdc -i "$TMP/$number.mmd" -o "$destination" -p "$PUPPETEER_JSON" -q 2>&1); then
    OK=$((OK + 1))
    printf '  \033[32mok\033[0m   %s (diagram %s, %s)\n' "$source" "$position" "$first"
  else
    FAILED=$((FAILED + 1))
    printf '  \033[31mFAIL\033[0m %s (diagram %s, %s)\n' "$source" "$position" "$first"
    printf '%s\n' "$error" | head -6 | sed 's/^/         /'
  fi
done < "$TMP/index.tsv"

echo
echo "──────────────────────────────────────────────"
if [[ $FAILED -eq 0 ]]; then
  printf '\033[32mAll %d diagrams parsed successfully.\033[0m\n' "$TOTAL"
  [[ $RENDER -eq 1 ]] && echo "SVGs written to docs/diagrams/out/"
  exit 0
fi
printf '\033[31m%d of %d diagrams failed to parse.\033[0m\n' "$FAILED" "$TOTAL"
exit 1