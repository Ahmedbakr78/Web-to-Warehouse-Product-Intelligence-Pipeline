import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Activity, Braces, Boxes, Download, Layers, Package, Star, Tags, TrendingUp, Wallet } from 'lucide-react'

import { AreaTrend, BarSeries, DonutChart, LineTrend, RadarCompare, HeatmapStrip } from '@/components/charts'
import {
  Badge,
  Button,
  Card,
  CardHeader,
  ChipGroup,
  DataTable,
  EmptyState,
  ErrorState,
  LoadingState,
  Segmented,
  Select,
  StatTile,
  Tabs,
} from '@/components/ui'
import { cn } from '@/lib/cn'
import { endpoints } from '@/lib/api'
import { useApiQuery } from '@/hooks/useApi'
import { downloadCsv, downloadJson, toCsv, formatCompact, formatDate, formatNumber, formatPrice } from '@/lib/format'

const RANGES = [
  { id: '14', label: '14d' },
  { id: '30', label: '30d' },
  { id: '90', label: '90d' },
  { id: '180', label: '180d' },
]

export default function Analytics() {
  const navigate = useNavigate()
  const [tab, setTab] = useState('categories')
  const [days, setDays] = useState('30')
  const windowDays = Number(days)
  const [selectedCategory, setSelectedCategory] = useState<string>('')
  const [brandLimit, setBrandLimit] = useState('15')

  const categories = useApiQuery(['analytics-categories'], () => endpoints.categories(20), { staleTime: 300_000 })
  const brands = useApiQuery(['analytics-brands', brandLimit], () => endpoints.brands(Number(brandLimit)), { staleTime: 300_000 })
  const availability = useApiQuery(['analytics-availability'], endpoints.availability, { staleTime: 300_000 })
  const index = useApiQuery(
    ['analytics-index', windowDays, selectedCategory],
    () => endpoints.categoryIndex(windowDays, selectedCategory || undefined),
  )
  const matrix = useApiQuery(['analytics-matrix'], endpoints.sourceMatrix, { staleTime: 600_000 })
  const trend = useApiQuery(['analytics-trend', windowDays], () => endpoints.trend(windowDays))
  const volatility = useApiQuery(['analytics-volatility'], () => endpoints.volatility(20, 3), { staleTime: 300_000 })
  const discounts = useApiQuery(['analytics-discounts'], () => endpoints.discounts(20), { staleTime: 300_000 })
  const topRated = useApiQuery(['analytics-top-rated'], () => endpoints.topRated(20), { staleTime: 300_000 })

  const categoryNames = useMemo(
    () => (categories.data ?? []).slice(0, 12).map((row: any) => ({ id: row.category_name, label: row.category_name, count: row.observations })),
    [categories.data],
  )

  const indexSeries = useMemo(() => {
    const rows = index.data ?? []
    const byCategory = new Map<string, any[]>()
    rows.forEach((row: any) => {
      const key = row.category_name ?? 'Unknown'
      if (!byCategory.has(key)) byCategory.set(key, [])
      byCategory.get(key)!.push(row)
    })
    const top = [...byCategory.entries()]
      .sort((a, b) => b[1].length - a[1].length)
      .slice(0, selectedCategory ? 1 : 5)
    const dates = [...new Set(rows.map((row: any) => formatDate(row.full_date)))]
    return {
      dates,
      data: dates.map((date) => {
        const point: Record<string, any> = { date }
        top.forEach(([name, items]) => {
          const match = items.find((item) => formatDate(item.full_date) === date)
          point[name] = match?.avg_price_usd ? Number(match.avg_price_usd) : null
        })
        return point
      }),
      names: top.map(([name]) => name),
    }
  }, [index.data, selectedCategory])

  const radarData = useMemo(() => {
    const topBrands = (brands.data ?? []).slice(0, 5)
    const axes = ['Price level', 'Rating', 'Coverage', 'Availability', 'Freshness']
    return axes.map((axis, indexPosition) => {
      const point: Record<string, any> = { axis }
      topBrands.forEach((brand: any) => {
        const prices = (categories.data ?? []).map((row: any) => Number(row.avg_price ?? 0)).filter(Boolean)
        const maxPrice = Math.max(1, ...prices)
        const maxCoverage = Math.max(1, ...topBrands.map((item: any) => Number(item.product_count ?? 0)))
        const axisScore: Record<string, number> = {
          'Price level': (Number(brand.avg_price_usd ?? 0) / maxPrice) * 100,
          Rating: (Number(brand.avg_rating ?? 0) / 5) * 100,
          Coverage: (Number(brand.product_count ?? 0) / maxCoverage) * 100,
          Availability: Number(brand.in_stock_observations ?? 0) > 0
            ? Math.min(100, (Number(brand.in_stock_observations) / Math.max(1, Number(brand.product_count))) * 100)
            : 40,
          Freshness: brand.last_seen_at ? Math.min(100, Math.max(30, 100 - (Date.now() - new Date(brand.last_seen_at).getTime()) / 86_400_000)) : 30,
        }
        point[brand.brand ?? `brand${indexPosition}`] = Math.round(axisScore[axis] ?? 0)
      })
      return point
    })
  }, [brands.data, categories.data])

  function exportCategories() {
    const header = ['category', 'observations', 'avg_price', 'min_price', 'max_price', 'avg_rating', 'new_products', 'price_changes']
    const body = (categories.data ?? []).map((row: any) => [
      row.category_name, row.observations, row.avg_price, row.min_price, row.max_price, row.avg_rating,
      row.new_products, row.price_changes,
    ])
    downloadCsv('category-analysis.csv', toCsv(header, body))
  }

  function exportJson() {
    downloadJson('category-analysis.json', {
      exported_at: new Date().toISOString(),
      window_days: windowDays,
      categories: categories.data ?? [],
      brands: brands.data ?? [],
      availability: availability.data ?? [],
    })
  }

  if (categories.isError) {
    return <ErrorState message={(categories.error as Error)?.message} onRetry={() => categories.refetch()} />
  }

  const totalObservations = (categories.data ?? []).reduce((sum, row) => sum + Number(row.observations ?? 0), 0)
  const totalNew = (categories.data ?? []).reduce((sum, row) => sum + Number(row.new_products ?? 0), 0)
  const totalChanges = (categories.data ?? []).reduce((sum, row) => sum + Number(row.price_changes ?? 0), 0)
  const avgPriceValues = (categories.data ?? []).map((row) => Number(row.avg_price ?? 0)).filter((value) => value > 0)
  const avgPrice = avgPriceValues.length ? avgPriceValues.reduce((a, b) => a + b, 0) / avgPriceValues.length : 0

  const availabilityData = (availability.data ?? []).slice(0, 10).map((row: any) => ({
    name: row.category_name,
    inStock: Number(row.in_stock_count ?? 0),
    outOfStock: Number(row.out_of_stock_count ?? 0),
    pct: Number(row.in_stock_pct ?? 0),
  }))

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Tabs
          active={tab}
          onChange={setTab}
          tabs={[
            { id: 'categories', label: 'Categories', icon: <Tags className="h-4 w-4" /> },
            { id: 'brands', label: 'Brands', icon: <Star className="h-4 w-4" /> },
            { id: 'leaders', label: 'Leaders', icon: <TrendingUp className="h-4 w-4" /> },
            { id: 'availability', label: 'Availability', icon: <Boxes className="h-4 w-4" /> },
            { id: 'sources', label: 'Source matrix', icon: <Layers className="h-4 w-4" /> },
          ]}
        />
        <div className="flex items-center gap-2">
          <Segmented options={RANGES} value={days} onChange={setDays} size="sm" />
          <Button size="sm" variant="secondary" icon={<Download className="h-4 w-4" />} onClick={exportCategories}>
            Export
          </Button>
          <Button size="sm" variant="ghost" icon={<Braces className="h-4 w-4" />} onClick={exportJson} aria-label="Export all analytics as JSON">
            JSON
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Observations" value={formatCompact(totalObservations)} hint="Across all tracked categories" icon={<Package className="h-4 w-4" />} />
        <StatTile label="Average price" value={formatPrice(avgPrice, 'USD')} hint="Mean of category averages" icon={<Wallet className="h-4 w-4" />} tone="info" />
        <StatTile label="New products" value={formatCompact(totalNew)} hint={`Last ${days} days`} icon={<TrendingUp className="h-4 w-4" />} tone="success" />
        <StatTile label="Price changes" value={formatCompact(totalChanges)} hint={`Last ${days} days`} icon={<Activity className="h-4 w-4" />} tone="warning" />
      </div>

      {/* ------------------------------------------------------------- category index */}
      <Card>
        <CardHeader
          title="Category price index"
          subtitle={`Average USD price per day over ${days} days`}
          icon={<TrendingUp className="h-4 w-4" />}
          action={
            <Select value={selectedCategory} onChange={(event) => setSelectedCategory(event.target.value)} aria-label="Category filter" className="h-8 w-48 py-0 text-xs">
              <option value="">All top categories</option>
              {(categories.data ?? []).map((row: any) => (
                <option key={row.category_name} value={row.category_name}>
                  {row.category_name}
                </option>
              ))}
            </Select>
          }
        />
        <ChipGroup options={[{ id: '', label: 'All' }, ...categoryNames]} value={selectedCategory} onChange={setSelectedCategory} className="mb-3" />
        {indexSeries.data.length ? (
          <LineTrend
            data={indexSeries.data}
            xKey="date"
            series={indexSeries.names.map((name) => ({ key: name, label: name }))}
            height={280}
            formatY="currency"
          />
        ) : (
          <EmptyState kind="chart" title="No price index data" message="Run more pipeline cycles to build up history." />
        )}
      </Card>

      {tab === 'categories' ? (
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
          <Card>
            <CardHeader title="Average price by category" subtitle="Top 12 categories" icon={<Wallet className="h-4 w-4" />} />
            {(categories.data ?? []).length ? (
              <BarSeries
                data={(categories.data ?? []).slice(0, 12).map((row: any) => ({ name: row.category_name, avg: Number(row.avg_price ?? 0) }))}
                xKey="name"
                bars={[{ key: 'avg', label: 'Average price', color: 'var(--chart-1)' }]}
                horizontal
                height={320}
                formatY="currency"
                onBarClick={(row) => row?.name && navigateToCategory(navigate, row.name)}
              />
            ) : (
              <LoadingState label="Loading categories…" rows={4} />
            )}
          </Card>

          <Card padded={false}>
            <div className="p-4 sm:p-5">
              <CardHeader title="Category breakdown" subtitle="Observations, pricing and movement" icon={<Tags className="h-4 w-4" />} />
            </div>
            <DataTable
              rows={categories.data ?? []}
              rowKey={(row: any) => row.category_name}
              loading={categories.isFetching}
              maxHeight={420}
              onRowClick={(row: any) => navigateToCategory(navigate, row.category_name)}
              columns={[
                { key: 'name', header: 'Category', render: (row: any) => <span className="font-medium">{row.category_name}</span> },
                { key: 'obs', header: 'Obs', align: 'right', sortValue: (row: any) => row.observations, render: (row: any) => formatCompact(row.observations) },
                { key: 'avg', header: 'Avg', align: 'right', sortValue: (row: any) => row.avg_price, render: (row: any) => formatPrice(row.avg_price) },
                { key: 'range', header: 'Range', align: 'right', hideBelow: 'md', render: (row: any) => `${formatPrice(row.min_price)} – ${formatPrice(row.max_price)}` },
                { key: 'rating', header: 'Rating', align: 'center', hideBelow: 'sm', render: (row: any) => (row.avg_rating ? Number(row.avg_rating).toFixed(1) : '—') },
                { key: 'new', header: 'New', align: 'right', hideBelow: 'lg', render: (row: any) => formatCompact(row.new_products ?? 0) },
                { key: 'changes', header: 'Changes', align: 'right', render: (row: any) => formatCompact(row.price_changes ?? 0) },
              ]}
            />
          </Card>
        </div>
      ) : null}

      {tab === 'brands' ? (
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
          <Card className="xl:col-span-2" padded={false}>
            <div className="p-4 sm:p-5">
              <CardHeader
                title="Brand leaderboard"
                subtitle="Coverage, pricing and rating"
                icon={<Star className="h-4 w-4" />}
                action={
                  <Select value={brandLimit} onChange={(event) => setBrandLimit(event.target.value)} aria-label="Brand limit" className="h-8 w-28 py-0 text-xs">
                    {[10, 15, 25, 40].map((value) => (
                      <option key={value} value={String(value)}>
                        Top {value}
                      </option>
                    ))}
                  </Select>
                }
              />
            </div>
            <DataTable
              rows={brands.data ?? []}
              rowKey={(row: any, index) => `${row.brand}-${row.category_name ?? index}`}
              loading={brands.isFetching}
              maxHeight={460}
              onRowClick={(row: any) => row.brand && navigate(`/products?brand=${encodeURIComponent(row.brand)}`)}
              columns={[
                { key: 'brand', header: 'Brand', render: (row: any) => <span className="font-medium">{row.brand}</span> },
                { key: 'category', header: 'Category', hideBelow: 'sm', render: (row: any) => <span className="text-xs text-muted">{row.category_name ?? '—'}</span> },
                { key: 'products', header: 'Products', align: 'right', sortValue: (row: any) => row.product_count, render: (row: any) => formatNumber(row.product_count ?? 0) },
                { key: 'avg', header: 'Avg price', align: 'right', sortValue: (row: any) => row.avg_price_usd, render: (row: any) => formatPrice(row.avg_price_usd) },
                { key: 'range', header: 'Range', align: 'right', hideBelow: 'lg', render: (row: any) => `${formatPrice(row.min_price_usd)} – ${formatPrice(row.max_price_usd)}` },
                { key: 'rating', header: 'Rating', align: 'center', sortValue: (row: any) => row.avg_rating, render: (row: any) => (row.avg_rating ? Number(row.avg_rating).toFixed(1) : '—') },
                { key: 'stock', header: 'In stock', align: 'right', hideBelow: 'md', render: (row: any) => formatCompact(row.in_stock_observations ?? 0) },
              ]}
            />
          </Card>

          <div className="space-y-3">
            <Card>
              <CardHeader title="Brand comparison" subtitle="Normalised 0-100 scores" icon={<Star className="h-4 w-4" />} />
              {(brands.data ?? []).length >= 3 ? (
                <RadarCompare
                  data={radarData}
                  series={(brands.data ?? []).slice(0, 5).map((brand: any) => ({ key: brand.brand, label: brand.brand }))}
                  height={280}
                />
              ) : (
                <EmptyState kind="products" title="Not enough brands to compare" />
              )}
            </Card>
            <Card>
              <CardHeader title="Observation heatmap" subtitle="Daily observation density" icon={<Activity className="h-4 w-4" />} />
              {(trend.data ?? []).length ? (
                <HeatmapStrip
                  data={(trend.data ?? []).slice(-60).map((row: any) => ({ label: String(row.full_date), value: Number(row.observations ?? 0) }))}
                  valueKey="value"
                  height={80}
                />
              ) : (
                <EmptyState kind="chart" title="No density data" />
              )}
            </Card>
          </div>
        </div>
      ) : null}

      {tab === 'leaders' ? (
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
          <Card padded={false} className="xl:col-span-2">
            <div className="p-4 sm:p-5">
              <CardHeader title="Price volatility" subtitle="Widest price range relative to average (min 3 observations)" icon={<Activity className="h-4 w-4" />} />
            </div>
            <DataTable
              rows={volatility.data ?? []}
              rowKey={(row: any) => `${row.product_id}-${row.source_code}`}
              loading={volatility.isFetching}
              maxHeight={380}
              onRowClick={(row: any) => navigate(`/products/${row.product_id}`)}
              columns={[
                { key: 'product', header: 'Product', render: (row: any) => <span className="font-medium">{row.canonical_name}</span> },
                { key: 'source', header: 'Source', hideBelow: 'sm', render: (row: any) => <Badge tone="neutral">{row.source_code}</Badge> },
                { key: 'range', header: 'Range', align: 'right', sortValue: (row: any) => row.range_pct, render: (row: any) => (row.range_pct == null ? '—' : `${Number(row.range_pct).toFixed(1)}%`) },
                { key: 'avg', header: 'Avg', align: 'right', hideBelow: 'md', render: (row: any) => formatPrice(row.avg_price_usd) },
                { key: 'minmax', header: 'Min – Max', align: 'right', hideBelow: 'lg', render: (row: any) => `${formatPrice(row.min_price_usd)} – ${formatPrice(row.max_price_usd)}` },
                { key: 'obs', header: 'Obs', align: 'right', render: (row: any) => formatNumber(row.observations ?? 0) },
              ]}
            />
          </Card>

          <Card padded={false}>
            <div className="p-4 sm:p-5">
              <CardHeader title="Discount leaders" subtitle="Deepest cuts off list price right now" icon={<Wallet className="h-4 w-4" />} />
            </div>
            <DataTable
              rows={discounts.data ?? []}
              rowKey={(row: any) => `${row.product_id}-${row.source_code}`}
              loading={discounts.isFetching}
              maxHeight={380}
              onRowClick={(row: any) => navigate(`/products/${row.product_id}`)}
              columns={[
                { key: 'product', header: 'Product', render: (row: any) => <span className="font-medium">{row.canonical_name}</span> },
                { key: 'off', header: 'Off', align: 'right', sortValue: (row: any) => row.discount_pct, render: (row: any) => <Badge tone="success">-{Number(row.discount_pct ?? 0).toFixed(0)}%</Badge> },
                { key: 'price', header: 'Price', align: 'right', render: (row: any) => formatPrice(row.price_usd) },
                { key: 'was', header: 'Was', align: 'right', hideBelow: 'md', render: (row: any) => formatPrice(row.list_price) },
              ]}
            />
          </Card>

          <Card padded={false}>
            <div className="p-4 sm:p-5">
              <CardHeader title="Top rated" subtitle="Best ratings, damped by vote count" icon={<Star className="h-4 w-4" />} />
            </div>
            <DataTable
              rows={topRated.data ?? []}
              rowKey={(row: any) => `${row.product_id}-${row.source_code}`}
              loading={topRated.isFetching}
              maxHeight={380}
              onRowClick={(row: any) => navigate(`/products/${row.product_id}`)}
              columns={[
                { key: 'product', header: 'Product', render: (row: any) => <span className="font-medium">{row.canonical_name}</span> },
                { key: 'rating', header: 'Rating', align: 'center', sortValue: (row: any) => row.damped_score, render: (row: any) => (row.rating == null ? '—' : `${Number(row.rating).toFixed(1)} ★ (${formatCompact(row.rating_count ?? 0)})`) },
                { key: 'price', header: 'Price', align: 'right', render: (row: any) => formatPrice(row.price_usd) },
                { key: 'brand', header: 'Brand', hideBelow: 'md', render: (row: any) => <span className="text-xs text-muted">{row.brand ?? '—'}</span> },
              ]}
            />
          </Card>
        </div>
      ) : null}

      {tab === 'availability' ? (
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
          <Card>
            <CardHeader title="In-stock ratio by category" subtitle="Share of observations that can be bought" icon={<Boxes className="h-4 w-4" />} />
            {availabilityData.length ? (
              <>
                <BarSeries
                  data={availabilityData}
                  xKey="name"
                  bars={[
                    { key: 'inStock', label: 'In stock', color: 'var(--chart-3)' },
                    { key: 'outOfStock', label: 'Out of stock', color: 'var(--chart-5)' },
                  ]}
                  stacked
                  height={320}
                  horizontal
                />
                <div className="mt-4 space-y-2">
                  {availabilityData.slice(0, 6).map((row) => (
                    <div key={row.name} className="flex items-center gap-3">
                      <span className="w-40 truncate text-xs text-muted">{row.name}</span>
                      <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-3">
                        <div className={cn('h-full rounded-full', row.pct >= 70 ? 'bg-success' : row.pct >= 40 ? 'bg-warning' : 'bg-danger')} style={{ width: `${row.pct}%` }} />
                      </div>
                      <span className="w-12 text-right text-xs font-medium tabular-nums">{row.pct.toFixed(0)}%</span>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <EmptyState kind="products" title="No availability data" />
            )}
          </Card>

          <Card>
            <CardHeader title="Out-of-stock pressure" subtitle="Categories with the most unavailable items" icon={<Boxes className="h-4 w-4" />} />
            {availabilityData.length ? (
              <DonutChart
                data={availabilityData.slice(0, 6).map((row) => ({ name: row.name, value: row.outOfStock }))}
                height={320}
                centerLabel="out of stock"
              />
            ) : (
              <EmptyState kind="chart" title="No data" />
            )}
          </Card>
        </div>
      ) : null}

      {tab === 'sources' ? (
        <Card padded={false}>
          <div className="p-4 sm:p-5">
            <CardHeader title="Source x category coverage" subtitle="How many products each source contributes per category" icon={<Layers className="h-4 w-4" />} />
          </div>
          <DataTable
            rows={matrix.data ?? []}
            rowKey={(row: any, index) => `${row.source_code}-${row.category_id ?? index}`}
            loading={matrix.isFetching}
            columns={[
              { key: 'source', header: 'Source', render: (row: any) => <Badge tone="neutral">{row.source_code}</Badge> },
              { key: 'category', header: 'Category', render: (row: any) => row.category_name ?? 'Uncategorised' },
              { key: 'products', header: 'Products', align: 'right', sortValue: (row: any) => row.products, render: (row: any) => formatNumber(row.products ?? 0) },
              { key: 'avg', header: 'Avg price', align: 'right', render: (row: any) => formatPrice(row.avg_price_usd) },
            ]}
          />
        </Card>
      ) : null}

      <AreaTrend
        data={(trend.data ?? []).map((row: any) => ({ ...row, date: formatDate(row.full_date) }))}
        xKey="date"
        series={[
          { key: 'avg_price_usd', label: 'Average price' },
          { key: 'in_stock_pct', label: 'In stock %' },
        ]}
        height={240}
        formatY="currency"
      />

      <p className="text-[11px] text-subtle">
        Every figure on this screen is produced by a SQL query over the 23 analytical views in{' '}
        <code className="rounded bg-surface-3 px-1">db/views.sql</code>.{' '}
        <Link to="/query" className="link">
          Inspect the queries
        </Link>
        .
      </p>
    </div>
  )
}

function navigateToCategory(navigate: (path: string) => void, category: string) {
  navigate(`/products?category=${encodeURIComponent(category)}`)
}