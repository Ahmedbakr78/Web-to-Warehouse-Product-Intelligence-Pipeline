import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Download, FolderTree, Layers, Package, Tags, TrendingUp } from 'lucide-react'

import { BarSeries } from '@/components/charts'
import {
  Badge,
  Button,
  Card,
  CardHeader,
  DataTable,
  EmptyState,
  ErrorState,
  LoadingState,
  SearchInput,
  StatTile,
  type Column,
} from '@/components/ui'
import { cn } from '@/lib/cn'
import { endpoints } from '@/lib/api'
import { useApiQuery } from '@/hooks/useApi'
import { downloadCsv, formatCompact, formatNumber, formatPrice, truncate } from '@/lib/format'

const TREE_GRID =
  'grid grid-cols-[minmax(0,1fr)_4.5rem_5.5rem] gap-2 md:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)_5rem_4.5rem_5.5rem]'

function compare(a: unknown, b: unknown, dir: 'asc' | 'desc') {
  const left = a === undefined ? null : a
  const right = b === undefined ? null : b
  if (left === right) return 0
  if (left === null) return 1
  if (right === null) return -1
  const result =
    typeof left === 'number' && typeof right === 'number'
      ? left - right
      : String(left).localeCompare(String(right))
  return dir === 'asc' ? result : -result
}

export default function Categories() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState('observations')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')

  const tree = useApiQuery(['categories-tree'], endpoints.categoriesTree)
  const breakdown = useApiQuery(['categories-breakdown', 20], () => endpoints.categories(20))

  function openCategory(name?: string | null) {
    if (!name) return
    void navigate(`/products?category=${encodeURIComponent(name)}`)
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
    const rows = breakdown.data ?? []
    const header = ['category', 'observations', 'avg_price', 'min_price', 'max_price', 'avg_rating', 'new_products', 'price_changes']
    const body = rows.map((row: any) => [
      row.category_name ?? '',
      row.observations ?? '',
      row.avg_price ?? '',
      row.min_price ?? '',
      row.max_price ?? '',
      row.avg_rating ?? '',
      row.new_products ?? '',
      row.price_changes ?? '',
    ])
    downloadCsv(
      'category-breakdown.csv',
      [header, ...body].map((line) => line.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(',')).join('\n'),
    )
  }

  const stats = useMemo(() => {
    const rows = tree.data ?? []
    const priced = rows.filter((row: any) => row.avg_price_usd !== null && row.avg_price_usd !== undefined)
    return {
      count: rows.length,
      active: rows.reduce((sum: number, row: any) => sum + Number(row.active_products ?? 0), 0),
      products: rows.reduce((sum: number, row: any) => sum + Number(row.product_count ?? 0), 0),
      priced: priced.length,
      avgPrice: priced.length
        ? priced.reduce((sum: number, row: any) => sum + Number(row.avg_price_usd), 0) / priced.length
        : null,
      depth: rows.reduce((max: number, row: any) => Math.max(max, Number(row.level ?? 1)), 0),
    }
  }, [tree.data])

  const visibleTree = useMemo(() => {
    const rows = tree.data ?? []
    const needle = search.trim().toLowerCase()
    if (!needle) return rows
    return rows.filter((row: any) => `${row.name ?? ''} ${row.path ?? ''}`.toLowerCase().includes(needle))
  }, [tree.data, search])

  const sortedBreakdown = useMemo(() => {
    const rows = [...(breakdown.data ?? [])]
    rows.sort((a: any, b: any) => compare(a?.[sortBy], b?.[sortBy], sortDir))
    return rows
  }, [breakdown.data, sortBy, sortDir])

  const topByPrice = useMemo(
    () =>
      (breakdown.data ?? [])
        .filter((row: any) => Number(row.avg_price ?? 0) > 0)
        .slice()
        .sort((a: any, b: any) => Number(b.avg_price) - Number(a.avg_price))
        .slice(0, 10)
        .map((row: any) => ({
          label: truncate(String(row.category_name ?? '\u2014'), 20),
          full_name: row.category_name,
          avg_price: Number(row.avg_price ?? 0),
        })),
    [breakdown.data],
  )

  const columns: Column<any>[] = [
    {
      key: 'category_name',
      header: 'Category',
      sortValue: (row) => row.category_name,
      render: (row) => (
        <button
          onClick={(event) => {
            event.stopPropagation()
            openCategory(row.category_name)
          }}
          className="block max-w-[16rem] text-left"
          title="Show the products of this category"
        >
          <span className="block truncate font-medium text-ink">{row.category_name ?? '\u2014'}</span>
          <span className="block text-[11px] text-subtle">{formatNumber(row.observations ?? 0)} observations</span>
        </button>
      ),
    },
    {
      key: 'observations',
      header: 'Obs.',
      align: 'right',
      sortValue: (row) => row.observations,
      render: (row) => <span className="tabular-nums">{formatNumber(row.observations ?? 0)}</span>,
    },
    {
      key: 'avg_price',
      header: 'Avg price',
      align: 'right',
      sortValue: (row) => row.avg_price,
      render: (row) => <span className="font-medium tabular-nums">{formatPrice(row.avg_price)}</span>,
    },
    {
      key: 'min_price',
      header: 'Min',
      align: 'right',
      hideBelow: 'sm',
      sortValue: (row) => row.min_price,
      render: (row) => <span className="tabular-nums text-muted">{formatPrice(row.min_price)}</span>,
    },
    {
      key: 'max_price',
      header: 'Max',
      align: 'right',
      hideBelow: 'md',
      sortValue: (row) => row.max_price,
      render: (row) => <span className="tabular-nums text-muted">{formatPrice(row.max_price)}</span>,
    },
    {
      key: 'avg_rating',
      header: 'Rating',
      align: 'right',
      hideBelow: 'lg',
      sortValue: (row) => row.avg_rating,
      render: (row) =>
        row.avg_rating === null || row.avg_rating === undefined ? (
          <span className="text-subtle">\u2014</span>
        ) : (
          <span className="tabular-nums">{Number(row.avg_rating).toFixed(2)}</span>
        ),
    },
    {
      key: 'new_products',
      header: 'New',
      align: 'right',
      hideBelow: 'sm',
      sortValue: (row) => row.new_products,
      render: (row) => <span className="tabular-nums text-success">{formatNumber(row.new_products ?? 0)}</span>,
    },
    {
      key: 'price_changes',
      header: 'Changes',
      align: 'right',
      hideBelow: 'lg',
      sortValue: (row) => row.price_changes,
      render: (row) => <span className="tabular-nums text-muted">{formatNumber(row.price_changes ?? 0)}</span>,
    },
    {
      key: 'open',
      header: '',
      align: 'right',
      hideBelow: 'xl',
      render: (row) => (
        <button
          onClick={(event) => {
            event.stopPropagation()
            openCategory(row.category_name)
          }}
          className="link text-xs"
        >
          Open
        </button>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      {/* ------------------------------------------------------------- toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SearchInput
          value={search}
          onChange={setSearch}
          placeholder="Filter the taxonomy by name or path\u2026"
          className="min-w-[14rem] max-w-md flex-1"
        />
        <Button size="sm" variant="secondary" icon={<Download className="h-4 w-4" />} onClick={exportCsv}>
          Export breakdown
        </Button>
      </div>

      {/* ------------------------------------------------------------- KPI cards */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Taxonomy nodes"
          value={formatNumber(stats.count)}
          hint={`${stats.depth} level${stats.depth === 1 ? '' : 's'} deep`}
          icon={<FolderTree className="h-4 w-4" />}
        />
        <StatTile
          label="Active products"
          value={formatCompact(stats.active)}
          hint={`of ${formatCompact(stats.products)} product assignments`}
          icon={<Package className="h-4 w-4" />}
          tone="info"
        />
        <StatTile
          label="Average price"
          value={formatPrice(stats.avgPrice)}
          hint="mean of the per-category averages"
          icon={<TrendingUp className="h-4 w-4" />}
          tone="warning"
        />
        <StatTile
          label="With price data"
          value={formatNumber(stats.priced)}
          hint={stats.count ? `${Math.round((stats.priced / stats.count) * 100)}% of the taxonomy priced` : 'no taxonomy yet'}
          icon={<Tags className="h-4 w-4" />}
          tone={stats.priced ? 'success' : 'neutral'}
        />
      </div>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        {/* ----------------------------------------------------------- taxonomy */}
        <Card className="xl:col-span-2" padded={false}>
          <div className="border-b border-line p-4 sm:p-5">
            <CardHeader
              title="Category taxonomy"
              subtitle={`${formatNumber(visibleTree.length)} node${visibleTree.length === 1 ? '' : 's'} \u00b7 select one to filter the product catalogue`}
              icon={<Layers className="h-4 w-4" />}
            />
          </div>

          {tree.isError ? (
            <div className="p-4">
              <ErrorState message={(tree.error as Error)?.message} onRetry={() => tree.refetch()} />
            </div>
          ) : tree.isLoading && !tree.data ? (
            <div className="p-4">
              <LoadingState label="Loading taxonomy\u2026" rows={5} />
            </div>
          ) : !tree.data?.length ? (
            <EmptyState title="No categories yet" message="Run the pipeline to build the category dimension." />
          ) : !visibleTree.length ? (
            <EmptyState
              title="No category matches this filter"
              message="Try a shorter term or clear the filter to see the whole taxonomy."
              action={
                <Button size="sm" variant="secondary" onClick={() => setSearch('')}>
                  Clear filter
                </Button>
              }
            />
          ) : (
            <div className="max-h-[32rem] overflow-auto">
              <div className={cn('sticky top-0 z-10 border-b border-line bg-surface-3 px-4 py-2', TREE_GRID)}>
                <span className="stat-label">Category</span>
                <span className="stat-label hidden md:block">Path</span>
                <span className="stat-label hidden text-right md:block">Products</span>
                <span className="stat-label text-right">Active</span>
                <span className="stat-label text-right">Avg price</span>
              </div>
              {visibleTree.map((row: any) => (
                <button
                  key={row.category_id}
                  onClick={() => openCategory(row.name)}
                  title={`Show the products of ${row.name}`}
                  className={cn(
                    'w-full border-b border-line px-4 py-1.5 text-left transition-colors hover:bg-surface-2',
                    TREE_GRID,
                  )}
                >
                  <span
                    className="flex min-w-0 items-center gap-2"
                    style={{ paddingLeft: search ? 0 : Math.max(0, (Number(row.level ?? 1) - 1) * 14) }}
                  >
                    <span className="truncate text-sm font-medium text-ink">{row.name}</span>
                    <Badge tone="neutral" className="shrink-0">
                      L{row.level ?? 1}
                    </Badge>
                  </span>
                  <span className="hidden truncate text-xs text-subtle md:block" title={row.path}>
                    {row.path ?? '\u2014'}
                  </span>
                  <span className="hidden text-right text-xs tabular-nums text-muted md:block">
                    {formatNumber(row.product_count ?? 0)}
                  </span>
                  <span className="text-right text-sm tabular-nums text-ink">{formatNumber(row.active_products ?? 0)}</span>
                  <span className="text-right text-sm tabular-nums text-ink">{formatPrice(row.avg_price_usd)}</span>
                </button>
              ))}
            </div>
          )}
        </Card>

        {/* -------------------------------------------------------- price chart */}
        <Card>
          <CardHeader
            title="Top categories by price"
            subtitle="Highest average USD price in the warehouse"
            icon={<TrendingUp className="h-4 w-4" />}
          />
          {breakdown.isError ? (
            <ErrorState message={(breakdown.error as Error)?.message} onRetry={() => breakdown.refetch()} />
          ) : breakdown.isLoading && !breakdown.data ? (
            <LoadingState label="Loading category aggregation\u2026" rows={4} />
          ) : topByPrice.length ? (
            <BarSeries
              data={topByPrice}
              xKey="label"
              bars={[{ key: 'avg_price', label: 'Average price (USD)' }]}
              horizontal
              formatY="currency"
              height={300}
              onBarClick={(entry: any) => openCategory(entry?.full_name)}
            />
          ) : (
            <EmptyState title="No price data yet" message="Prices appear once the first snapshots are loaded." />
          )}
        </Card>
      </div>

      {/* ------------------------------------------------------------- breakdown */}
      <Card padded={false}>
        <div className="p-4 sm:p-5">
          <CardHeader
            title="Category breakdown"
            subtitle="Aggregated daily roll-up behind every category figure"
            icon={<Tags className="h-4 w-4" />}
          />
        </div>
        <DataTable
          rows={sortedBreakdown}
          rowKey={(row: any) => `${row.category_id ?? row.category_name}`}
          loading={breakdown.isFetching && !breakdown.isError}
          onSort={onSort}
          sort={{ by: sortBy, dir: sortDir }}
          onRowClick={(row) => openCategory(row.category_name)}
          emptyMessage="No category aggregation available yet"
          columns={columns}
        />
      </Card>
    </div>
  )
}
