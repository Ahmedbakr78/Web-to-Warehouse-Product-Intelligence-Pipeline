#!/usr/bin/env bash
# Extract every Mermaid diagram from the documentation into docs/diagrams/out so it can be
# rendered by mermaid-cli (mmdc) or shared with tools that do not render Mermaid inline.
#
#   bash scripts/render_diagrams.sh           # extract diagrams only
#   DOCS_RENDER=1 bash scripts/render_diagrams.sh   # also render SVGs when mmdc is installed
#
# GitHub renders the inline diagrams natively; this script is for offline tool chains.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/docs/diagrams/out"
mkdir -p "$OUT"

extracted=0
idx="$OUT/index.md"
: >"$idx"
echo "# Extracted Mermaid diagrams" >"$idx"
echo >>"$idx"
echo "| Source | Diagram | File |" | tee -a "$idx" >/dev/null
echo "| --- | --- | --- |" | tee -a "$idx" >/dev/null

while IFS=$'\t' read -r src rel slug; do
  n=0
  block=""
  active=0
  in_fence=1
  name="$slug"
  while IFS= read -r line; do
    case "$line" in
      '```mermaid'*)
        active=1
        n=$((n + 1))
        block=""
        in_fence=0
        file="$OUT/${name}_${n}.mmd"
        ;;
      '```'* )
        if [ "$active" -eq 1 ]; then
          printf '%s\n' "$block" >"$file"
          printf '%s' "$block" | tail -n +1 | grep -q . || true
          end_line=$(printf '%s' "$block" | head -n 1 | cut -c1-52)
          printf '| %s | %s | `%s` |\n' "$rel" "$end_line" "$(basename "$file")" | tee -a "$idx" >/dev/null
          extracted=$((extracted + 1))
          active=0
          block=""
          in_fence=1
        fi
        ;;
      *)
        if [ "$active" -eq 1 ]; then
          block="${block}${line}"$'\n'
        fi
        ;;
    esac
  done <"$src"
  :
done < <(
  cd "$ROOT" &&
  find docs README.md CONTRIBUTING.md CHANGELOG.md -name '*.md' -type f 2>/dev/null | while read -r f; do
    rel="${f#./}"
    slug="$(printf '%s' "$rel" | tr '/ .' '__-' | tr -cd 'a-zA-Z0-9_-' )"
    printf '%s\t%s\t%s\n' "$ROOT/$rel" "$rel" "$slug"
  done
)

echo "extracted $extracted diagrams -> $OUT" >&2
echo "index written: $OUT/index.md" >&2

if [ "${DOCS_RENDER:-0}" = "1" ]; then
  if command -v mmdc >/dev/null 2>&1; then
    for f in "$OUT"/*.mmd; do
      case "$f" in *"index.md"*) continue ;; esac
      svg="${f%.mmd}.svg"
      echo "rendering $(basename "$f") -> $(basename "$svg")" >&2
      mmdc -i "$f" -o "$svg" --quiet || echo "warning: render failed for $f" >&2
    done
  else
    echo "mmdc not installed; install with 'npm i -g @mermaid-js/mermaid-cli' to render SVGs" >&2
  fi
fi
