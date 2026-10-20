import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Activity, ArrowDownRight, ArrowUpRight, Braces, Layers, Package, Tag, Trash2, Zap } from 'lucide-react'

import { BarSeries, LineTrend } from '@/components/charts'
import {
  Badge,
  Button,
  Card,
  CardHeader,
  DataTable,
  DeltaPill,
  EmptyState,
  ErrorState,
  LoadingState,
  Pagination,
  SearchInput,
  Segmented,
  Select,
  StatTile,
  Tabs,
} from '@/components/ui'
import { ExportButton } from '@/components/ExportButton'
import { endpoints } from '@/lib/api'
import { useApiQuery } from '@/hooks/useApi'
import { useDebounce } from '@/hooks/useDebounce'
import { downloadJson, formatCompact, formatDate, formatNumber, formatPrice, formatRelative, statusTone, titleCase } from '@/lib/format'

const RANGES = [
  { id: '7', label: '7d' },
  { id: '30', label: '30d' },
  { id: '90', label: '90d' },
  { id: '365', label: '1y' },
]

const EVENT_TABS = [
  { id: 'price', label: 'Price changes' },
  { id: 'events', label: 'Lifecycle' },
  { id: 'new', label: 'New' },
  { id: 'removed', label: 'Removed' },
  { id: 'categories', label: 'Recategorised' },
]

export default function Changes() {
  const [tab, setTab] = useState('price')
  const [days, setDays] = useState('30')
  const windowDays = Number(days)
  const [direction, setDirection] = useState('')
  const [category, setCategory] = useState('')
  const [significantOnly, setSignificantOnly] = useState(false)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  const [sortBy, setSortBy] = useState('change_pct')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')

  const debouncedSearch = useDebounce(search, 300)

  const summary = useApiQuery(['change-summary', windowDays], () => endpoints.changeSummary(windowDays))
  const timeline = useApiQuery(['price-change-timeline', windowDays], () => endpoints.priceTrend(windowDays))
  const movers = useApiQuery(['top-movers', 12], () => endpoints.topMovers(12))
  const drift = useApiQuery(['category-drift', windowDays], () => endpoints.categoryDrift(windowDays))

  const priceParams = useMemo(
    () => ({
      page,
      page_size: pageSize,
      days: windowDays,
      sort_by: sortBy,
      sort_dir: sortDir,
      direction: direction || undefined,
      category: category || undefined,
      significant_only: significantOnly || undefined,
    }),
    [page, pageSize, windowDays, sortBy, sortDir, direction, category, significantOnly],
  )
  const priceChanges = useApiQuery(['price-changes', priceParams], () => endpoints.priceChanges(priceParams))

  const eventsParams = useMemo(() => ({ page, page_size: pageSize, days: windowDays }), [page, pageSize, windowDays])
  const events = useApiQuery(['events', eventsParams], () => endpoints.events(eventsParams))
  const newProducts = useApiQuery(['new-products', windowDays], () => endpoints.newProducts(windowDays, 100))
  const removed = useApiQuery(['removed-products', windowDays], () => endpoints.removedProducts(windowDays, 100))
  const categoryChanges = useApiQuery(['category-changes', windowDays], () => endpoints.categoryChanges(windowDays, 100))

  const timelineData = (timeline.data ?? []).map((row: any) => ({ ...row, date: formatDate(row.full_date) }))

  function onSort(key: string) {
    if (sortBy === key) setSortDir((current) => (current === 'asc' ? 'desc' : 'asc'))
    else {
      setSortBy(key)
      setSortDir('desc')
    }
  }

  if (priceChanges.isError) {
    return <ErrorState message={(priceChanges.error as Error)?.message} onRetry={() => priceChanges.refetch()} />
  }

  const searchFilter = (rows: any[]) =>
    debouncedSearch
      ? rows.filter((row) => `${row.canonical_name ?? ''} ${row.brand ?? ''} ${row.category_name ?? ''}`.toLowerCase().includes(debouncedSearch.toLowerCase()))
      : rows

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Segmented options={RANGES} value={days} onChange={setDays} size="sm" />
        <div className="flex flex-wrap items-center gap-2">
          <SearchInput value={search} onChange={(value) => { setSearch(value); setPage(1) }} placeholder="Filter results…" className="w-56" />
          <Select value={direction} onChange={(event) => { setDirection(event.target.value); setPage(1) }} aria-label="Direction" className="w-32">
            <option value="">All directions</option>
            <option value="increase">Increases</option>
            <option value="decrease">Decreases</option>
          </Select>
          <Button size="sm" variant={significantOnly ? 'primary' : 'secondary'} icon={<Zap className="h-4 w-4" />} onClick={() => { setSignificantOnly((value) => !value); setPage(1) }}>
            Significant only
          </Button>
          <Button
            size="sm"
            variant="ghost"
            icon={<Braces className="h-4 w-4" />}
            aria-label="Export current feed as JSON"
            onClick={() =>
              downloadJson('change-feed.json', {
                exported_at: new Date().toISOString(),
                window_days: windowDays,
                summary: summary.data,
                price_changes: (priceChanges.data as any)?.items ?? [],
                new_products: newProducts.data ?? [],
                removed_products: removed.data ?? [],
                category_changes: categoryChanges.data ?? [],
              })
            }
          >
            JSON
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Total events" value={formatCompact(summary.data?.total_events ?? 0)} hint={`Last ${days} days`} icon={<Activity className="h-4 w-4" />} />
        <StatTile label="Price increases" value={formatCompact(summary.data?.price_changes ?? 0)} hint="Detected between snapshots" icon={<ArrowUpRight className="h-4 w-4" />} tone="danger" />
        <StatTile label="New products" value={formatCompact(summary.data?.new_products ?? 0)} hint="First time seen" icon={<Package className="h-4 w-4" />} tone="success" />
        <StatTile label="Removed products" value={formatCompact(summary.data?.removed_products ?? 0)} hint="No longer listed" icon={<Trash2 className="h-4 w-4" />} tone="warning" />
      </div>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader
            title="Change activity"
            subtitle="Daily increases and decreases"
            icon={<Activity className="h-4 w-4" />}
            action={<ExportButton dataset="price_changes" />}
          />
          {timelineData.length ? (
            <BarSeries
              data={timelineData}
              xKey="date"
              bars={[
                { key: 'decreases', label: 'Decreases', color: 'var(--chart-3)' },
                { key: 'increases', label: 'Increases', color: 'var(--chart-5)' },
              ]}
              stacked
              height={240}
            />
          ) : (
            <EmptyState kind="price" title="No change activity in this window" />
          )}
        </Card>

        <Card>
          <CardHeader title="Average move size" subtitle="Absolute percentage change per day" icon={<Activity className="h-4 w-4" />} />
          {timelineData.length ? (
            <LineTrend
              data={timelineData}
              xKey="date"
              series={[
                { key: 'avg_abs_change_pct', label: 'Avg |change| %', color: 'var(--chart-4)' },
                { key: 'max_abs_change_pct', label: 'Max |change| %', color: 'var(--chart-5)' },
              ]}
              height={240}
              formatY="percent"
            />
          ) : (
            <EmptyState kind="price" title="No data" />
          )}
        </Card>
      </div>

      <Tabs
        active={tab}
        onChange={(value) => { setTab(value); setPage(1) }}
        tabs={EVENT_TABS.map((item) => ({
          ...item,
          count:
            item.id === 'events' ? (events.data?.total ?? undefined)
            : item.id === 'price' ? (priceChanges.data?.total ?? undefined)
            : item.id === 'new' ? (newProducts.data?.length ?? undefined)
            : item.id === 'removed' ? (removed.data?.length ?? undefined)
            : (categoryChanges.data?.length ?? undefined),
        }))}
      />

      {tab === 'price' ? (
        <Card padded={false}>
          <div className="p-3">
            <div className="flex flex-wrap items-center gap-2">
              <SearchInput value={category} onChange={setCategory} placeholder="Filter by category…" className="w-56" />
              <div className="ml-auto text-xs text-subtle">
                {formatNumber(priceChanges.data?.total ?? 0)} changes · sorted by {sortBy} ({sortDir})
              </div>
            </div>
          </div>
          <DataTable
            rows={searchFilter(priceChanges.data?.items ?? [])}
            rowKey={(row: any) => String(row.change_id)}
            loading={priceChanges.isFetching}
            onSort={onSort}
            sort={{ by: sortBy, dir: sortDir }}
            emptyMessage="No price changes match these filters"
            columns={[
              {
                key: 'product',
                header: 'Product',
                sortValue: (row: any) => row.canonical_name,
                render: (row: any) => (
                  <Link to={`/products/${row.product_id}`} className="block max-w-[20rem]">
                    <span className="block truncate font-medium">{row.canonical_name}</span>
                    <span className="block truncate text-[11px] text-subtle">
                      {row.brand ? `${row.brand} · ` : ''}
                      {row.category_name ?? 'Uncategorised'}
                    </span>
                  </Link>
                ),
              },
              { key: 'from', header: 'From', align: 'right', hideBelow: 'sm', sortValue: (row: any) => row.previous_price, render: (row: any) => <span className="tabular-nums">{formatPrice(row.previous_price)}</span> },
              { key: 'to', header: 'To', align: 'right', sortValue: (row: any) => row.new_price, render: (row: any) => <span className="tabular-nums font-medium">{formatPrice(row.new_price)}</span> },
              {
                key: 'change_pct',
                header: 'Change',
                align: 'right',
                render: (row: any) => (
                  <span className="flex items-center justify-end gap-2">
                    <span className="tabular-nums text-xs text-muted">{row.change_abs ? Number(row.change_abs).toFixed(2) : '—'}</span>
                    <DeltaPill value={row.change_pct} />
                  </span>
                ),
              },
              {
                key: 'direction',
                header: 'Direction',
                hideBelow: 'md',
                render: (row: any) => (
                  <Badge tone={row.direction === 'decrease' ? 'success' : 'danger'}>
                    {row.direction === 'decrease' ? <ArrowDownRight className="h-3 w-3" /> : <ArrowUpRight className="h-3 w-3" />}
                    {titleCase(row.direction)}
                  </Badge>
                ),
              },
              { key: 'band', header: 'Band', align: 'center', hideBelow: 'lg', render: (row: any) => <Badge tone="neutral">{row.magnitude_band ?? '—'}</Badge> },
              { key: 'source', header: 'Source', hideBelow: 'xl', render: (row: any) => <Badge tone="neutral">{row.source_code}</Badge> },
              { key: 'date', header: 'Detected', align: 'right', hideBelow: 'md', render: (row: any) => formatDate(row.full_date ?? row.detected_at) },
            ]}
          />
          <div className="p-3">
            <Pagination page={page} pageSize={pageSize} total={priceChanges.data?.total ?? 0} onPage={setPage} onPageSize={setPageSize} />
          </div>
        </Card>
      ) : null}

      {tab === 'events' ? (
        <Card padded={false}>
          <DataTable
            rows={searchFilter(events.data?.items ?? [])}
            rowKey={(row: any) => String(row.event_id)}
            loading={events.isFetching}
            emptyMessage="No lifecycle events in this window"
            columns={[
              { key: 'product', header: 'Product', render: (row: any) => <Link to={`/products/${row.product_id}`} className="block max-w-[20rem] truncate font-medium">{row.canonical_name}</Link> },
              { key: 'type', header: 'Event', render: (row: any) => <Badge tone={statusTone(row.event_type === 'removed' ? 'failed' : row.event_type === 'new' ? 'success' : 'info')}>{titleCase(row.event_type)}</Badge> },
              { key: 'severity', header: 'Severity', hideBelow: 'sm', render: (row: any) => <Badge tone={row.severity === 'warning' ? 'warning' : 'neutral'}>{titleCase(row.severity ?? 'info')}</Badge> },
              { key: 'old', header: 'Old', hideBelow: 'lg', render: (row: any) => <span className="tabular-nums text-xs">{row.old_value ?? '—'}</span> },
              { key: 'new', header: 'New', hideBelow: 'lg', render: (row: any) => <span className="tabular-nums text-xs font-medium">{row.new_value ?? '—'}</span> },
              { key: 'source', header: 'Source', hideBelow: 'xl', render: (row: any) => <Badge tone="neutral">{row.source_code}</Badge> },
              { key: 'detected', header: 'Detected', align: 'right', render: (row: any) => formatRelative(row.detected_at) },
            ]}
          />
          <div className="p-3">
            <Pagination page={page} pageSize={pageSize} total={events.data?.total ?? 0} onPage={setPage} onPageSize={setPageSize} />
          </div>
        </Card>
      ) : null}

      {tab === 'new' ? (
        <Card padded={false}>
          <DataTable
            rows={searchFilter(newProducts.data ?? [])}
            rowKey={(row: any) => String(row.product_id)}
            loading={newProducts.isFetching}
            emptyMessage="No new products discovered in this window"
            columns={[
              { key: 'product', header: 'Product', render: (row: any) => <Link to={`/products/${row.product_id}`} className="block max-w-[22rem] truncate font-medium">{row.canonical_name}</Link> },
              { key: 'brand', header: 'Brand', hideBelow: 'sm', render: (row: any) => row.brand ?? '—' },
              { key: 'category', header: 'Category', hideBelow: 'md', render: (row: any) => <Badge tone="neutral">{row.category_name ?? 'Uncategorised'}</Badge> },
              { key: 'price', header: 'Price', align: 'right', render: (row: any) => formatPrice(row.price_usd ?? row.price, row.currency ?? 'USD') },
              { key: 'rating', header: 'Rating', align: 'center', hideBelow: 'lg', render: (row: any) => (row.rating ? Number(row.rating).toFixed(1) : '—') },
              { key: 'first', header: 'First seen', align: 'right', render: (row: any) => formatRelative(row.first_seen_at) },
            ]}
          />
        </Card>
      ) : null}

      {tab === 'removed' ? (
        <Card padded={false}>
          <DataTable
            rows={searchFilter(removed.data ?? [])}
            rowKey={(row: any) => String(row.product_id)}
            loading={removed.isFetching}
            emptyMessage="No products have been removed in this window"
            columns={[
              { key: 'product', header: 'Product', render: (row: any) => <Link to={`/products/${row.product_id}`} className="block max-w-[22rem]"><span className="block truncate font-medium">{row.canonical_name}</span><span className="block truncate text-[11px] text-subtle">{row.brand ?? ''}</span></Link> },
              { key: 'category', header: 'Category', hideBelow: 'sm', render: (row: any) => <Badge tone="neutral">{row.category_name ?? 'Uncategorised'}</Badge> },
              { key: 'lastprice', header: 'Last price', align: 'right', render: (row: any) => formatPrice(row.last_known_price_usd) },
              { key: 'rating', header: 'Last rating', align: 'center', hideBelow: 'md', render: (row: any) => (row.last_known_rating ? Number(row.last_known_rating).toFixed(1) : '—') },
              { key: 'missing', header: 'Missing (days)', align: 'right', hideBelow: 'lg', render: (row: any) => formatNumber(row.days_missing ?? 0) },
              { key: 'removed', header: 'Removed', align: 'right', render: (row: any) => formatDate(row.removed_date) },
            ]}
          />
        </Card>
      ) : null}

      {tab === 'categories' ? (
        <div className="space-y-3">
          <Card padded={false}>
            <div className="p-4 sm:p-5">
              <CardHeader title="Category recategorisations" subtitle="Products whose upstream category changed" icon={<Tag className="h-4 w-4" />} />
            </div>
            <DataTable
              rows={searchFilter(categoryChanges.data ?? [])}
              rowKey={(row: any) => String(row.event_id)}
              loading={categoryChanges.isFetching}
              emptyMessage="No recategorisations detected"
              columns={[
                { key: 'product', header: 'Product', render: (row: any) => <Link to={`/products/${row.product_id}`} className="block max-w-[22rem] truncate font-medium">{row.canonical_name}</Link> },
                { key: 'from', header: 'From', render: (row: any) => <Badge tone="neutral">{row.old_category ?? '—'}</Badge> },
                { key: 'to', header: 'To', render: (row: any) => <Badge tone="brand">{row.new_category ?? '—'}</Badge> },
                { key: 'source', header: 'Source', hideBelow: 'md', render: (row: any) => <Badge tone="neutral">{row.source_code}</Badge> },
                { key: 'date', header: 'Changed', align: 'right', render: (row: any) => formatDate(row.change_date) },
              ]}
            />
          </Card>

          <Card padded={false}>
            <div className="p-4 sm:p-5">
              <CardHeader title="Assortment drift" subtitle="Products added, removed and recategorised per category" icon={<Layers className="h-4 w-4" />} />
            </div>
            <DataTable
              rows={drift.data ?? []}
              rowKey={(row: any) => row.category_name}
              loading={drift.isFetching}
              maxHeight={420}
              columns={[
                { key: 'category', header: 'Category', render: (row: any) => <span className="font-medium">{row.category_name}</span> },
                { key: 'added', header: 'Added', align: 'right', sortValue: (row: any) => row.products_added, render: (row: any) => <span className="text-success">+{formatNumber(row.products_added ?? 0)}</span> },
                { key: 'removed', header: 'Removed', align: 'right', sortValue: (row: any) => row.products_removed, render: (row: any) => <span className="text-danger">-{formatNumber(row.products_removed ?? 0)}</span> },
                { key: 'recat', header: 'Recategorised', align: 'right', hideBelow: 'sm', sortValue: (row: any) => row.products_recategorised, render: (row: any) => formatNumber(row.products_recategorised ?? 0) },
                {
                  key: 'net',
                  header: 'Net',
                  align: 'right',
                  sortValue: (row: any) => row.net_change,
                  render: (row: any) => (
                    <Badge tone={(row.net_change ?? 0) > 0 ? 'success' : (row.net_change ?? 0) < 0 ? 'danger' : 'neutral'}>
                      {Number(row.net_change ?? 0) > 0 ? '+' : ''}
                      {formatNumber(row.net_change ?? 0)}
                    </Badge>
                  ),
                },
              ]}
            />
          </Card>
        </div>
      ) : null}

      {priceChanges.isLoading && !priceChanges.data ? <LoadingState label="Loading change feed…" rows={6} /> : null}

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Card padded={false}>
          <div className="p-4 sm:p-5">
            <CardHeader title="Top movers this window" subtitle="Largest absolute percentage moves" icon={<Activity className="h-4 w-4" />} />
          </div>
          <DataTable
            rows={movers.data ?? []}
            rowKey={(row: any, index) => `${row.product_id}-${index}`}
            loading={movers.isFetching}
            maxHeight={320}
            columns={[
              { key: 'product', header: 'Product', render: (row: any) => <Link to={`/products/${row.product_id}`} className="block max-w-[18rem] truncate text-sm">{row.canonical_name}</Link> },
              { key: 'change', header: 'Change', align: 'right', render: (row: any) => <DeltaPill value={row.change_pct} /> },
            ]}
          />
        </Card>

        <Card>
          <CardHeader title="How changes are detected" subtitle="Pipeline logic" icon={<Activity className="h-4 w-4" />} />
          <ol className="space-y-2 text-xs text-muted">
            {[
              'Each run compares the newest snapshot of every product against the previous one (same product, same source).',
              'A non-zero difference becomes a chg_price_change row with direction, magnitude band and a significance flag (|Δ| ≥ 2%).',
              'A product seen for the first time emits a "new" lifecycle event; a product missing for more than the staleness window emits "removed".',
              'A product whose dim_product.category_id changes emits "category_changed" with the old and new category.',
              'The SQL views vw_price_changes, vw_new_products, vw_removed_products and vw_category_changes expose all of it to this screen.',
            ].map((step, index) => (
              <li key={index} className="flex gap-2">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand-100 text-[10px] font-semibold text-brand-700 dark:bg-brand-500/20 dark:text-brand-300">
                  {index + 1}
                </span>
                <span className="leading-relaxed">{step}</span>
              </li>
            ))}
          </ol>
        </Card>
      </div>
    </div>
  )
}