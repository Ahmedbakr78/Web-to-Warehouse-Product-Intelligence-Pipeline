/**
 * Product comparison workspace.
 *
 * Up to four products are compared side by side using the existing product and
 * history endpoints. The selected ids live in the URL, so a comparison is
 * bookmarkable and shareable without any server state. Everything loads in
 * place - no full-page navigation and no decorative animation.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQueries } from '@tanstack/react-query'
import { ArrowLeft, ClipboardCopy, ExternalLink, Link2, Plus, Search, Trash2, X } from 'lucide-react'

import { Badge, Button, Card, EmptyState, IconButton, LoadingState, Sparkline, useToast } from '@/components/ui'
import { DEFAULT_OPTIONS } from '@/hooks/useApi'
import { comparisonWinners, copyText, compareUrl, comparisonMarkdown, COMPARE_LIMIT, parseCompareIds } from '@/lib/share'
import { endpoints, searchProducts } from '@/lib/api'
import { formatAvailability, formatDate, formatPrice, formatRelative } from '@/lib/format'
import { cn } from '@/lib/cn'

type Product = Record<string, any>

function Field({ label, children, tone }: { label: string; children: React.ReactNode; tone?: string }) {
  return (
    <div className="rounded-lg border border-line bg-surface-2 px-2.5 py-2">
      <dt className="stat-label mb-1">{label}</dt>
      <dd className={cn('text-xs font-medium text-ink', tone)}>{children}</dd>
    </div>
  )
}

function CompareColumn({
  product,
  history,
  cheapestId,
  topRatedId,
  onRemove,
}: {
  product: Product
  history: number[]
  cheapestId: number | null
  topRatedId: number | null
  onRemove: () => void
}) {
  const id = Number(product.product_id)
  const availability = formatAvailability(product.availability)
  const price = product.price_usd === null || product.price_usd === undefined ? null : Number(product.price_usd)
  const rating = product.rating === null || product.rating === undefined ? null : Number(product.rating)

  return (
    <Card className="flex min-w-[15rem] flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          {product.product_url ? (
            <a className="link truncate text-sm font-semibold" href={product.product_url} target="_blank" rel="noreferrer">
              {product.canonical_name ?? `Product #${id}`}
              <ExternalLink className="ml-1 inline h-3 w-3" aria-hidden />
            </a>
          ) : (
            <p className="truncate text-sm font-semibold text-ink">{product.canonical_name ?? `Product #${id}`}</p>
          )}
          <p className="mt-0.5 text-[11px] text-subtle">#{id} · {product.source_code ?? 'unknown source'}</p>
        </div>
        <IconButton label={`Remove product ${id} from comparison`} icon={<X className="h-4 w-4" />} onClick={onRemove} />
      </div>

      <div className="flex flex-wrap gap-1.5">
        {product.category_name ? <Badge tone="brand">{product.category_name}</Badge> : null}
        {product.brand ? <Badge tone="neutral">{product.brand}</Badge> : null}
        {product.availability ? <Badge tone={availability.tone}>{availability.label}</Badge> : null}
        {id === cheapestId ? <Badge tone="success">Best price</Badge> : null}
        {id === topRatedId ? <Badge tone="info">Top rated</Badge> : null}
      </div>

      <dl className="grid grid-cols-2 gap-2">
        <Field label="Price (USD)" tone={id === cheapestId ? 'text-success' : undefined}>
          {price === null ? '—' : formatPrice(price, 'USD')}
        </Field>
        <Field label="Rating" tone={id === topRatedId ? 'text-info' : undefined}>
          {rating === null ? '—' : `${rating.toFixed(2)}${product.rating_count ? ` (${product.rating_count})` : ''}`}
        </Field>
        <Field label="Source">{product.source_code ?? '—'}</Field>
        <Field label="Last seen">{formatRelative(product.last_seen_at ?? product.updated_at)}</Field>
      </dl>

      <div>
        <p className="stat-label mb-1">Price trend</p>
        {history.length > 1 ? (
          <Sparkline values={history} className="h-10 w-full" />
        ) : (
          <p className="text-[11px] text-subtle">Not enough snapshots yet</p>
        )}
      </div>
    </Card>
  )
}

export default function Compare() {
  const [params, setParams] = useSearchParams()
  const ids = useMemo(() => parseCompareIds(params.get('ids')), [params])
  const [term, setTerm] = useState('')
  const [matches, setMatches] = useState<Array<Record<string, unknown>>>([])
  const toast = useToast()
  const timer = useRef<number | null>(null)

  // Replace (not push) keeps the back button useful while the selection changes.
  function setIds(next: number[]) {
    const clean = parseCompareIds(next.join(','))
    setParams(clean.length ? { ids: clean.join(',') } : {}, { replace: true })
  }

  useEffect(() => () => {
    if (timer.current !== null) window.clearTimeout(timer.current)
  }, [])

  useEffect(() => {
    const q = term.trim()
    if (q.length < 2) {
      setMatches([])
      return
    }
    if (timer.current !== null) window.clearTimeout(timer.current)
    const controller = new AbortController()
    timer.current = window.setTimeout(() => {
      searchProducts(q, controller.signal)
        .then((response) => setMatches((response?.items ?? []).filter((item) => !ids.includes(Number(item.product_id)))))
        .catch((error: Error) => {
          if (error.name !== 'AbortError') setMatches([])
        })
    }, 220)
    return () => {
      controller.abort()
      if (timer.current !== null) window.clearTimeout(timer.current)
    }
  }, [term, ids])

  const products = useQueries({
    queries: ids.map((id) => ({
      queryKey: ['product', id],
      queryFn: () => endpoints.product(id),
      ...DEFAULT_OPTIONS,
    })),
  })
  const histories = useQueries({
    queries: ids.map((id) => ({
      queryKey: ['product-history', id],
      queryFn: () => endpoints.productHistory(id, 60),
      ...DEFAULT_OPTIONS,
    })),
  })

  const loaded = products
    .map((result) => result.data as Product | undefined)
    .filter((product): product is Product => Boolean(product))
  const { cheapestId, topRatedId } = comparisonWinners(loaded)

  const loading = products.some((result) => result.isLoading) || histories.some((result) => result.isLoading)

  async function copyLink() {
    const ok = await copyText(`${window.location.origin}${compareUrl(ids)}`)
    toast[ok ? 'success' : 'error'](ok ? 'Comparison link copied' : 'Could not copy the link')
  }

  async function copyMarkdown() {
    const columns = [
      { key: 'name', label: 'Product' },
      { key: 'category', label: 'Category' },
      { key: 'price', label: 'Price (USD)' },
      { key: 'rating', label: 'Rating' },
      { key: 'availability', label: 'Availability' },
      { key: 'source', label: 'Source' },
    ]
    const rows = loaded.map((product) => ({
      name: product.canonical_name,
      category: product.category_name,
      price: product.price_usd === null ? null : formatPrice(Number(product.price_usd), 'USD'),
      rating: product.rating,
      availability: formatAvailability(product.availability).label,
      source: product.source_code,
    }))
    const ok = await copyText(comparisonMarkdown(rows, columns))
    toast[ok ? 'success' : 'error'](ok ? 'Comparison copied as Markdown' : 'Could not copy the comparison')
  }

  function add(id: number) {
    if (ids.includes(id)) return
    if (ids.length >= COMPARE_LIMIT) {
      toast.warning(`You can compare up to ${COMPARE_LIMIT} products`)
      return
    }
    setIds([...ids, id])
    setTerm('')
    setMatches([])
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Link to="/products" className="btn btn-ghost h-9 w-9 !p-0" aria-label="Back to products">
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <div>
            <h2 className="text-base font-semibold text-ink">Product comparison</h2>
            <p className="text-xs text-subtle">Up to {COMPARE_LIMIT} products, side by side · shareable by link</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="secondary" icon={<Link2 className="h-4 w-4" />} onClick={() => void copyLink()} disabled={!ids.length}>
            Copy link
          </Button>
          <Button size="sm" variant="secondary" icon={<ClipboardCopy className="h-4 w-4" />} onClick={() => void copyMarkdown()} disabled={!loaded.length}>
            Copy Markdown
          </Button>
          <Button size="sm" variant="ghost" icon={<Trash2 className="h-4 w-4" />} onClick={() => setIds([])} disabled={!ids.length}>
            Clear
          </Button>
        </div>
      </div>

      <Card>
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-subtle" aria-hidden />
          <input
            className="w-full rounded-lg border border-line bg-surface-2 py-2 pl-9 pr-3 text-sm text-ink outline-none placeholder:text-subtle focus:border-brand"
            placeholder="Search products to add (at least 2 characters)…"
            value={term}
            onChange={(event) => setTerm(event.target.value)}
            aria-label="Search products to compare"
          />
        </div>
        {matches.length ? (
          <ul className="mt-2 divide-y divide-line">
            {matches.map((item) => {
              const id = Number(item.product_id)
              return (
                <li key={id}>
                  <button
                    className="flex w-full items-center justify-between gap-2 px-1 py-2 text-left text-xs hover:bg-surface-2"
                    onClick={() => add(id)}
                  >
                    <span className="min-w-0 truncate text-ink">{String(item.canonical_name ?? `Product #${id}`)}</span>
                    <span className="flex shrink-0 items-center gap-2 text-subtle">
                      {item.price_usd !== null && item.price_usd !== undefined ? formatPrice(Number(item.price_usd), 'USD') : '—'}
                      <Plus className="h-3.5 w-3.5" aria-hidden />
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        ) : null}
      </Card>

      {loading && !loaded.length ? <LoadingState label="Loading products…" rows={3} /> : null}

      {!ids.length ? (
        <EmptyState
          kind="search"
          title="No products selected"
          message="Search above to add products, or open a shared comparison link."
        />
      ) : (
        <div className="flex gap-3 overflow-x-auto pb-2">
          {ids.map((id, index) => {
            const product = products[index]?.data as Product | undefined
            const history = ((histories[index]?.data as any)?.history ?? []) as Array<Record<string, unknown>>
            const values = history
              .map((row) => (row.price_usd === null || row.price_usd === undefined ? null : Number(row.price_usd)))
              .filter((value): value is number => Number.isFinite(value))
            if (!product) {
              return (
                <Card key={id} className="flex min-w-[15rem] flex-col gap-3">
                  <p className="text-xs text-subtle">Loading product #{id}…</p>
                </Card>
              )
            }
            return (
              <CompareColumn
                key={id}
                product={product}
                history={values}
                cheapestId={cheapestId}
                topRatedId={topRatedId}
                onRemove={() => setIds(ids.filter((item) => item !== id))}
              />
            )
          })}
          {ids.length < COMPARE_LIMIT ? (
            <div className="flex min-w-[12rem] items-center justify-center rounded-2xl border border-dashed border-line text-xs text-subtle">
              Add another product to compare
            </div>
          ) : null}
        </div>
      )}

      {loaded.length ? (
        <p className="text-[11px] text-subtle">
          Comparing {loaded.length} of {ids.length} products · prices normalised to USD · snapshots refreshed {formatDate(new Date().toISOString())}
        </p>
      ) : null}
    </div>
  )
}
