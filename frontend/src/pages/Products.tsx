import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Columns3, Download, Filter, Package, RotateCcw, Star } from 'lucide-react'

import {
  Badge,
  Button,
  Card,
  ChipGroup,
  DataTable,
  DeltaPill,
  EmptyState,
  ErrorState,
  LoadingState,
  Modal,
  Pagination,
  SearchInput,
  Select,
  Toggle,
  type Tone,
} from '@/components/ui'
import { cn } from '@/lib/cn'
import { endpoints } from '@/lib/api'
import { useApiQuery } from '@/hooks/useApi'
import { useDebounce } from '@/hooks/useDebounce'
import { localStore } from '@/lib/session'
import {
  downloadCsv,
  formatAvailability,
  formatDateTime,
  formatNumber,
  formatPrice,
  formatRelative,
} from '@/lib/format'

type ColumnKey =
  | 'name'
  | 'category'
  | 'brand'
  | 'price'
  | 'change'
  | 'rating'
  | 'availability'
  | 'source'
  | 'last_seen'
  | 'observations'
  | 'url'

const ALL_COLUMNS: { key: ColumnKey; label: string }[] = [
  { key: 'name', label: 'Product' },
  { key: 'category', label: 'Category' },
  { key: 'brand', label: 'Brand' },
  { key: 'price', label: 'Price' },
  { key: 'change', label: 'Change' },
  { key: 'rating', label: 'Rating' },
  { key: 'availability', label: 'Availability' },
  { key: 'source', label: 'Source' },
  { key: 'last_seen', label: 'Last seen' },
  { key: 'observations', label: 'Observations' },
  { key: 'url', label: 'Link' },
]

const STOCK_FILTERS = [
  { id: '', label: 'All' },
  { id: 'true', label: 'In stock' },
  { id: 'false', label: 'Out of stock' },
]

export default function Products() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [search, setSearch] = useState(searchParams.get('q') ?? '')
  const [page, setPage] = useState(Number(searchParams.get('page') ?? 1))
  const [pageSize, setPageSize] = useState(() => localStore.get('products.pageSize', 25))
  const [sortBy, setSortBy] = useState<string>('last_seen_at')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [stock, setStock] = useState(searchParams.get('in_stock') ?? '')
  const [category, setCategory] = useState(searchParams.get('category') ?? '')
  const [brand, setBrand] = useState(searchParams.get('brand') ?? '')
  const [source, setSource] = useState(searchParams.get('source') ?? '')
  const [availability, setAvailability] = useState('')
  const [priceMin, setPriceMin] = useState('')
  const [priceMax, setPriceMax] = useState('')
  const [minRating, setMinRating] = useState('')
  const [activeOnly, setActiveOnly] = useState(true)
  const [showFilters, setShowFilters] = useState(false)
  const [showColumns, setShowColumns] = useState(false)
  const [columns, setColumns] = useState<ColumnKey[]>(() =>
    localStore.get<ColumnKey[]>('products.columns', ['name', 'category', 'brand', 'price', 'change', 'availability', 'last_seen']),
  )

  const debouncedSearch = useDebounce(search, 320)

  useEffect(() => {
    localStore.set('products.columns', columns)
  }, [columns])

  useEffect(() => {
    const next: Record<string, string> = {}
    if (debouncedSearch) next.q = debouncedSearch
    if (page > 1) next.page = String(page)
    if (stock) next.in_stock = stock
    if (category) next.category = category
    if (brand) next.brand = brand
    if (source) next.source = source
    setSearchParams(next, { replace: true })
  }, [debouncedSearch, page, stock, category, brand, source, setSearchParams])

  useEffect(() => {
    setPage(1)
  }, [debouncedSearch, stock, category, brand, source, availability, priceMin, priceMax, minRating, activeOnly])

  const params = useMemo(
    () => ({
      page,
      page_size: pageSize,
      sort_by: sortBy,
      sort_dir: sortDir,
      q: debouncedSearch || undefined,
      in_stock: stock || undefined,
      category: category || undefined,
      brand: brand || undefined,
      source: source || undefined,
      availability: availability || undefined,
      min_price: priceMin || undefined,
      max_price: priceMax || undefined,
      min_rating: minRating || undefined,
      is_active: activeOnly ? true : undefined,
    }),
    [page, pageSize, sortBy, sortDir, debouncedSearch, stock, category, brand, source, availability, priceMin, priceMax, minRating, activeOnly],
  )

  const products = useApiQuery(['products', params], () => endpoints.products(params))
  const facets = useApiQuery(['facets'], endpoints.facets, { staleTime: 300_000 })

  const rows = products.data?.items ?? []
  const total = products.data?.total ?? 0

  const activeFilterCount = [category, brand, source, availability, priceMin, priceMax, minRating, stock].filter(Boolean).length

  function resetFilters() {
    setSearch('')
    setStock('')
    setCategory('')
    setBrand('')
    setSource('')
    setAvailability('')
    setPriceMin('')
    setPriceMax('')
    setMinRating('')
    setActiveOnly(true)
    setPage(1)
  }

  function onSort(key: string) {
    if (sortBy === key) {
      setSortDir((current) => (current === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortBy(key)
      setSortDir('desc')
    }
  }

  function exportCsv() {
    const header: any[] = ['product_id', 'name', 'category', 'brand', 'price', 'currency', 'change_pct', 'rating', 'availability', 'source', 'last_seen']
    const body: any[][] = rows.map((row: any) => [
      row.product_id,
      row.canonical_name,
      row.category_name ?? '',
      row.brand ?? '',
      row.price_usd ?? '',
      row.currency ?? '',
      row.price_change_pct ?? '',
      row.rating ?? '',
      row.availability ?? '',
      row.source_code ?? '',
      row.last_seen_at ?? '',
    ])
    downloadCsv('products.csv', [header, ...body].map((line) => line.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(',')).join('\n'))
  }

  const visible = (key: ColumnKey) => columns.includes(key)

  return (
    <div className="space-y-3">
      {/* ------------------------------------------------------------- toolbar */}
      <Card padded={false} className="p-3">
        <div className="flex flex-wrap items-center gap-2">
          <SearchInput value={search} onChange={setSearch} placeholder="Search name, brand or category\u2026" className="min-w-[16rem] flex-1" />
          <ChipGroup options={STOCK_FILTERS} value={stock} onChange={setStock} />
          <div className="ml-auto flex items-center gap-2">
            <Button size="sm" variant={showFilters ? 'primary' : 'secondary'} icon={<Filter className="h-4 w-4" />} onClick={() => setShowFilters((value) => !value)}>
              Filters{activeFilterCount ? ` (${activeFilterCount})` : ''}
            </Button>
            <Button size="sm" variant="secondary" icon={<Columns3 className="h-4 w-4" />} onClick={() => setShowColumns(true)}>
              Columns
            </Button>
            <Button size="sm" variant="secondary" icon={<Download className="h-4 w-4" />} onClick={exportCsv}>
              CSV
            </Button>
          </div>
        </div>

        {showFilters ? (
          <div className="mt-3 grid grid-cols-2 gap-2 border-t border-line pt-3 sm:grid-cols-3 lg:grid-cols-6">
            <Select value={category} onChange={(event) => setCategory(event.target.value)} aria-label="Category">
              <option value="">All categories</option>
              {facets.data?.categories?.map((item: any) => (
                <option key={item.category_name} value={item.category_name}>
                  {item.category_name} ({item.count})
                </option>
              ))}
            </Select>
            <Select value={brand} onChange={(event) => setBrand(event.target.value)} aria-label="Brand">
              <option value="">All brands</option>
              {facets.data?.brands?.slice(0, 60).map((item: any) => (
                <option key={item.brand} value={item.brand}>
                  {item.brand} ({item.count})
                </option>
              ))}
            </Select>
            <Select value={source} onChange={(event) => setSource(event.target.value)} aria-label="Source">
              <option value="">All sources</option>
              {facets.data?.sources?.map((item: any) => (
                <option key={item.source_code} value={item.source_code}>
                  {item.source_code} ({item.count})
                </option>
              ))}
            </Select>
            <Select value={availability} onChange={(event) => setAvailability(event.target.value)} aria-label="Availability">
              <option value="">Any availability</option>
              {facets.data?.availability?.map((item: any) => (
                <option key={item.availability} value={item.availability}>
                  {item.availability} ({item.count})
                </option>
              ))}
            </Select>
            <div className="flex items-center gap-1">
              <input className="input" placeholder="Min" inputMode="decimal" value={priceMin} onChange={(event) => setPriceMin(event.target.value)} aria-label="Minimum price" />
              <input className="input" placeholder="Max" inputMode="decimal" value={priceMax} onChange={(event) => setPriceMax(event.target.value)} aria-label="Maximum price" />
            </div>
            <div className="flex items-center gap-2">
              <Select value={minRating} onChange={(event) => setMinRating(event.target.value)} aria-label="Minimum rating">
                <option value="">Any rating</option>
                <option value="3">3+ stars</option>
                <option value="4">4+ stars</option>
                <option value="4.5">4.5+ stars</option>
              </Select>
              <Button size="sm" variant="ghost" icon={<RotateCcw className="h-3.5 w-3.5" />} onClick={resetFilters} aria-label="Reset filters" />
            </div>
          </div>
        ) : null}
      </Card>

      {/* ------------------------------------------------------------- table */}
      {products.isError ? (
        <ErrorState message={(products.error as Error)?.message} onRetry={() => products.refetch()} />
      ) : products.isLoading && !products.data ? (
        <LoadingState label="Loading products…" rows={8} />
      ) : rows.length === 0 ? (
        <Card>
          <EmptyState
            title="No products match these filters"
            message="Try removing a filter, widening the price range or searching for a different term."
            icon={<Package className="h-8 w-8" />}
            action={
              activeFilterCount || search ? (
                <Button size="sm" variant="secondary" onClick={resetFilters}>
                  Clear all filters
                </Button>
              ) : null
            }
          />
        </Card>
      ) : (
        <>
          <DataTable
            rows={rows}
            rowKey={(row: any) => String(row.product_id)}
            loading={products.isFetching}
            onSort={onSort}
            sort={{ by: sortBy, dir: sortDir }}
            columns={[
              ...(visible('name')
                ? [
                    {
                      key: 'name',
                      header: 'Product',
                      sortValue: (row: any) => row.canonical_name,
                      render: (row: any) => (
                        <Link to={`/products/${row.product_id}`} className="flex items-center gap-2.5">
                          {row.image_url ? (
                            <img
                              src={row.image_url}
                              alt=""
                              loading="lazy"
                              className="h-8 w-8 shrink-0 rounded-md border border-line object-contain"
                              onError={(event) => {
                                ;(event.currentTarget as HTMLImageElement).style.visibility = 'hidden'
                              }}
                            />
                          ) : (
                            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-surface-3 text-subtle">
                              <Package className="h-4 w-4" aria-hidden />
                            </span>
                          )}
                          <span className="min-w-0">
                            <span className="block max-w-[18rem] truncate font-medium">{row.canonical_name}</span>
                            {visible('brand') && row.brand ? (
                              <span className="block text-[11px] text-subtle">{row.brand}</span>
                            ) : null}
                          </span>
                        </Link>
                      ),
                    },
                  ]
                : []),
              ...(visible('category')
                ? [
                    {
                      key: 'category',
                      header: 'Category',
                      hideBelow: 'sm' as const,
                      render: (row: any) => (
                        <span className="max-w-[10rem] truncate text-xs text-muted" title={row.category_path ?? row.category_name ?? ''}>
                          {row.category_name ?? 'Uncategorised'}
                        </span>
                      ),
                    },
                  ]
                : []),
              ...(visible('price')
                ? [
                    {
                      key: 'price',
                      header: 'Price',
                      align: 'right' as const,
                      sortValue: (row: any) => row.price_usd,
                      render: (row: any) => (
                        <span className="font-medium tabular-nums">{formatPrice(row.price_usd ?? row.price, row.currency ?? 'USD')}</span>
                      ),
                    },
                  ]
                : []),
              ...(visible('change')
                ? [
                    {
                      key: 'change',
                      header: 'Change',
                      align: 'right' as const,
                      sortValue: (row: any) => row.price_change_pct,
                      render: (row: any) => <DeltaPill value={row.price_change_pct} />,
                    },
                  ]
                : []),
              ...(visible('rating')
                ? [
                    {
                      key: 'rating',
                      header: 'Rating',
                      align: 'center' as const,
                      hideBelow: 'md' as const,
                      sortValue: (row: any) => row.rating,
                      render: (row: any) =>
                        row.rating !== null && row.rating !== undefined ? (
                          <span className="inline-flex items-center gap-1 tabular-nums">
                            <Star className="h-3.5 w-3.5 text-warning" aria-hidden />
                            {Number(row.rating).toFixed(1)}
                          </span>
                        ) : (
                          <span className="text-subtle">\u2014</span>
                        ),
                    },
                  ]
                : []),
              ...(visible('availability')
                ? [
                    {
                      key: 'availability',
                      header: 'Availability',
                      sortValue: (row: any) => row.availability,
                      render: (row: any) => {
                        const availabilityInfo = formatAvailability(row.availability)
                        return <Badge tone={availabilityInfo.tone as Tone}>{availabilityInfo.label}</Badge>
                      },
                    },
                  ]
                : []),
              ...(visible('source')
                ? [
                    {
                      key: 'source',
                      header: 'Source',
                      hideBelow: 'lg' as const,
                      render: (row: any) => <Badge tone="neutral">{row.source_code ?? '\u2014'}</Badge>,
                    },
                  ]
                : []),
              ...(visible('observations')
                ? [
                    {
                      key: 'observations',
                      header: 'Obs.',
                      align: 'right' as const,
                      hideBelow: 'lg' as const,
                      sortValue: (row: any) => row.observation_count,
                      render: (row: any) => formatNumber(row.observation_count ?? 0),
                    },
                  ]
                : []),
              ...(visible('last_seen')
                ? [
                    {
                      key: 'last_seen',
                      header: 'Last seen',
                      align: 'right' as const,
                      sortValue: (row: any) => (row.last_seen_at ? new Date(row.last_seen_at).getTime() : 0),
                      render: (row: any) => (
                        <span title={formatDateTime(row.last_seen_at)} className="text-xs text-muted">
                          {formatRelative(row.last_seen_at)}
                        </span>
                      ),
                    },
                  ]
                : []),
              ...(visible('url')
                ? [
                    {
                      key: 'url',
                      header: '',
                      align: 'right' as const,
                      hideBelow: 'xl' as const,
                      render: (row: any) =>
                        row.product_url ? (
                          <a
                            href={row.product_url}
                            target="_blank"
                            rel="noreferrer noopener"
                            className="link text-xs"
                            onClick={(event) => event.stopPropagation()}
                          >
                            open
                          </a>
                        ) : (
                          <span className="text-subtle">\u2014</span>
                        ),
                    },
                  ]
                : []),
            ]}
          />
          <Pagination page={page} pageSize={pageSize} total={total} onPage={setPage} onPageSize={(size) => { setPageSize(size); localStore.set('products.pageSize', size) }} />
        </>
      )}

      {/* ------------------------------------------------------------- column picker */}
      <Modal open={showColumns} onClose={() => setShowColumns(false)} title="Visible columns" description="Pick which columns appear in the table." size="sm">
        <div className="space-y-2">
          {ALL_COLUMNS.map((column) => (
            <Toggle
              key={column.key}
              checked={columns.includes(column.key)}
              onChange={(checked) =>
                setColumns((current) => (checked ? [...current, column.key] : current.filter((item) => item !== column.key)))
              }
              label={column.label}
            />
          ))}
          <div className="flex justify-between border-t border-line pt-3">
            <Button size="sm" variant="ghost" onClick={() => setColumns(ALL_COLUMNS.map((column) => column.key))}>
              Select all
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setColumns(['name', 'category', 'price'])}>
              Minimal
            </Button>
          </div>
        </div>
      </Modal>

      <div className={cn('flex items-center justify-between text-[11px] text-subtle')}>
        <span>
          {formatNumber(total)} products \u00b7 dedupe threshold 0.90 \u00b7 fuzzy matching with jaro-winkler, token-set
          and trigram similarity
        </span>
        <span>Active products only: {activeOnly ? 'yes' : 'no'}</span>
      </div>
    </div>
  )
}