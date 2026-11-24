/**
 * Shareable-link and clipboard helpers used by the comparison workspace and the
 * command palette. Kept free of React so the encoding rules can be unit-tested.
 */

/** The maximum number of products a comparison can hold. */
export const COMPARE_LIMIT = 4

/** Parse `?ids=1,2,3` into a bounded list of unique, positive product ids. */
export function parseCompareIds(raw: string | null | undefined): number[] {
  if (!raw) return []
  const ids: number[] = []
  for (const part of raw.split(',')) {
    const id = Number(part.trim())
    if (Number.isInteger(id) && id > 0 && !ids.includes(id)) ids.push(id)
    if (ids.length >= COMPARE_LIMIT) break
  }
  return ids
}

/** Build the canonical comparison URL for a set of ids. */
export function compareUrl(ids: number[], pathname = '/compare'): string {
  return `${pathname}?ids=${parseCompareIds(ids.join(',')).join(',')}`
}

/** Write text to the clipboard, with a fallback for non-secure browser contexts. */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // Fall through to the legacy path (e.g. an insecure localhost context).
  }
  try {
    const area = document.createElement('textarea')
    area.value = text
    area.setAttribute('readonly', '')
    area.style.position = 'fixed'
    area.style.opacity = '0'
    document.body.appendChild(area)
    area.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(area)
    return ok
  } catch {
    return false
  }
}

/**
 * The cheapest and top-rated product ids in a comparison.
 *
 * Missing values are ignored rather than treated as zero: `Number(null)` is 0,
 * which would otherwise make a product without a price win "Best price".
 */
export function comparisonWinners(
  products: Array<Record<string, any>>,
): { cheapestId: number | null; topRatedId: number | null } {
  const priced = products
    .filter((product) => product.price_usd !== null && product.price_usd !== undefined)
    .map((product) => ({ id: Number(product.product_id), value: Number(product.price_usd) }))
    .filter((item) => Number.isFinite(item.value))
  const rated = products
    .filter((product) => product.rating !== null && product.rating !== undefined)
    .map((product) => ({ id: Number(product.product_id), value: Number(product.rating) }))
    .filter((item) => Number.isFinite(item.value))
  return {
    cheapestId: priced.length ? priced.reduce((a, b) => (a.value <= b.value ? a : b)).id : null,
    topRatedId: rated.length ? rated.reduce((a, b) => (a.value >= b.value ? a : b)).id : null,
  }
}

/** A compact Markdown table of the compared products (safe for chat and docs). */
export function comparisonMarkdown(
  rows: Array<Record<string, string | number | null | undefined>>,
  columns: Array<{ key: string; label: string }>,
): string {
  if (!rows.length) return '_No products selected._'
  const cell = (value: string | number | null | undefined): string =>
    String(value ?? '—').replace(/\|/g, '\\|').replace(/\n/g, ' ')
  const header = `| ${columns.map((column) => column.label).join(' | ')} |`
  const rule = `| ${columns.map(() => '---').join(' | ')} |`
  const body = rows.map((row) => `| ${columns.map((column) => cell(row[column.key])).join(' | ')} |`)
  return [header, rule, ...body].join('\n')
}
