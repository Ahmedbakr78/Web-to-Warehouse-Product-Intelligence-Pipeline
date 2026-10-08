import { Link } from 'react-router-dom'
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  Boxes,
  Braces,
  Clock,
  Download,
  Gauge,
  Layers,
  Package,
  RefreshCw,
  ShieldCheck,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { AreaTrend, BarSeries, DonutChart, LineTrend } from '@/components/charts'
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
  Segmented,
  StatTile,
} from '@/components/ui'
import { cn } from '@/lib/cn'
import { endpoints } from '@/lib/api'
import { useApiQuery } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import {
  downloadCsv,
  downloadJson,
  toCsv,
  formatCompact,
  formatDate,
  formatDuration,
  formatNumber,
  formatPercent,
  formatPrice,
  formatRelative,
  statusTone,
} from '@/lib/format'

const RANGES = [
  { id: '7', label: '7d' },
  { id: '30', label: '30d' },
  { id: '90', label: '90d' },
  { id: '180', label: '180d' },
]

export default function Dashboard() {
  const [days, setDays] = useState('30')
  const windowDays = Number(days)
  const queryClient = useQueryClient()
  const { can } = useAuth()

  const kpi = useApiQuery(['kpi', windowDays], () => endpoints.kpi(windowDays))
  const trend = useApiQuery(['trend', windowDays], () => endpoints.trend(windowDays))
  const priceTrend = useApiQuery(['price-trend', windowDays], () => endpoints.priceTrend(windowDays))
  const movers = useApiQuery(['top-movers', 8], () => endpoints.topMovers(8))
  const quality = useApiQuery(['quality-latest'], endpoints.qualityLatest)
  const latestRun = useApiQuery(['run-latest'], endpoints.runLatest)
  const changeSummary = useApiQuery(['change-summary', windowDays], () => endpoints.changeSummary(windowDays))

  const refresh = useMutation({
    mutationFn: async () => {
      await queryClient.invalidateQueries()
    },
  })

  if (kpi.isError) {
    return <ErrorState message={(kpi.error as Error)?.message} onRetry={() => kpi.refetch()} />
  }
  if (kpi.isLoading && !kpi.data) return <LoadingState label="Loading dashboard…" rows={6} />

  const latest = kpi.data?.latest ?? {}
  const changes = kpi.data?.changes ?? {}
  const events = kpi.data?.events ?? {}
  const counts = kpi.data?.counts ?? {}
  const qualityScore = quality.data?.score ?? latest.dq_score ?? null

  const trendData = (trend.data ?? []).map((row: any) => ({
    ...row,
    date: formatDate(row.full_date),
    avg_price_usd: row.avg_price_usd ? Number(row.avg_price_usd) : null,
  }))

  const priceChangeData = (priceTrend.data ?? []).map((row: any) => ({
    ...row,
    date: formatDate(row.full_date),
  }))

  const availabilityMix = [
    { name: 'In stock', value: Math.max(0, Number(latest.in_stock_count ?? 0)) },
    {
      name: 'Other states',
      value: Math.max(0, Number(latest.products ?? 0) - Number(latest.in_stock_count ?? 0)),
    },
  ]

  function exportCsv() {
    const rows = movers.data ?? []
    const header = ['product', 'category', 'previous_price', 'new_price', 'change_pct', 'direction', 'source', 'date']
    const body = rows.map((row: any) => [
      row.canonical_name,
      row.category_name ?? '',
      row.previous_price ?? '',
      row.new_price ?? '',
      row.change_pct ?? '',
      row.direction ?? '',
      row.source_code ?? '',
      row.full_date ?? '',
    ])
    downloadCsv('top-movers.csv', toCsv(header, body))
  }

  function exportJson() {
    downloadJson('dashboard-snapshot.json', {
      exported_at: new Date().toISOString(),
      window_days: windowDays,
      kpi: kpi.data,
      top_movers: movers.data ?? [],
      change_summary: changeSummary.data,
      quality: quality.data,
    })
  }

  return (
    <div className="space-y-4">
      {/* ------------------------------------------------------------- toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Segmented options={RANGES} value={days} onChange={setDays} size="sm" />
        <div className="flex items-center gap-2">
          <Button size="sm" variant="secondary" icon={<Download className="h-4 w-4" />} onClick={exportCsv}>
            Export movers
          </Button>
          <Button size="sm" variant="ghost" icon={<Braces className="h-4 w-4" />} onClick={exportJson} aria-label="Export snapshot as JSON">
            Snapshot
          </Button>
          <Button
            size="sm"
            variant="ghost"
            icon={<RefreshCw className={cn('h-4 w-4', refresh.isPending && 'animate-spin')} />}
            onClick={() => refresh.mutate()}
          >
            Refresh
          </Button>
        </div>
      </div>

      {/* ------------------------------------------------------------- KPI cards */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Products observed"
          value={formatCompact(latest.products ?? 0)}
          hint={`${formatNumber(counts.dim_product ?? 0)} canonical in warehouse`}
          icon={<Package className="h-4 w-4" />}
        />
        <StatTile
          label="Average price"
          value={formatPrice(latest.avg_price ?? null, 'USD')}
          hint={`min ${formatPrice(latest.min_price ?? null)} · max ${formatPrice(latest.max_price ?? null)}`}
          icon={<TrendingUp className="h-4 w-4" />}
          tone="info"
        />
        <StatTile
          label="Price changes"
          value={formatCompact(changes.total_changes ?? 0)}
          hint={`${formatCompact(changes.decreases ?? 0)} down · ${formatCompact(changes.increases ?? 0)} up`}
          icon={<Activity className="h-4 w-4" />}
          tone="warning"
          delta={<DeltaPill value={changes.avg_abs_change_pct ?? null} />}
        />
        <StatTile
          label="Data quality score"
          value={qualityScore !== null ? `${qualityScore}` : '—'}
          hint={`${quality.data?.pass ?? 0} pass · ${quality.data?.warn ?? 0} warn · ${quality.data?.fail ?? 0} fail`}
          icon={<ShieldCheck className="h-4 w-4" />}
          tone={qualityScore === null ? 'neutral' : qualityScore >= 90 ? 'success' : qualityScore >= 75 ? 'warning' : 'danger'}
        />
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="New products"
          value={formatCompact(events.new ?? 0)}
          hint={`arrivals in the last ${days} days`}
          icon={<ArrowUpRight className="h-4 w-4" />}
          tone="success"
        />
        <StatTile
          label="Removed products"
          value={formatCompact(events.removed ?? 0)}
          hint={`delisted or out of circulation`}
          icon={<ArrowDownRight className="h-4 w-4" />}
          tone="danger"
        />
        <StatTile
          label="Category changes"
          value={formatCompact(events.category_changed ?? 0)}
          hint="products recategorised upstream"
          icon={<Layers className="h-4 w-4" />}
          tone="warning"
        />
        <StatTile
          label="Sources reporting"
          value={formatNumber(latest.sources ?? 0)}
          hint={`last observation ${formatRelative(latest.last_observation_at)}`}
          icon={<Boxes className="h-4 w-4" />}
          tone="info"
        />
      </div>

      {/* ------------------------------------------------------------- charts */}
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader
            title="Market price and coverage trend"
            subtitle={`Daily averages over the last ${days} days`}
            icon={<TrendingUp className="h-4 w-4" />}
          />
          {trendData.length ? (
            <AreaTrend
              data={trendData}
              xKey="date"
              series={[
                { key: 'avg_price_usd', label: 'Average price (USD)' },
                { key: 'observations', label: 'Observations' },
              ]}
              height={280}
              formatY="currency"
            />
          ) : (
            <EmptyState kind="chart" title="No trend data yet" message="Run the pipeline to populate the warehouse." />
          )}
        </Card>

        <Card>
          <CardHeader title="Availability mix" subtitle="Share of in-stock observations" icon={<Boxes className="h-4 w-4" />} />
          {Number(latest.products ?? 0) > 0 ? (
            <>
              <DonutChart data={availabilityMix} height={200} centerLabel="observations" />
              <div className="mt-3 space-y-1.5 text-xs">
                {availabilityMix.map((item, index) => (
                  <div key={item.name} className="flex items-center gap-2">
                    <span
                      className="h-2.5 w-2.5 rounded-full"
                      style={{ backgroundColor: index === 0 ? 'var(--chart-3)' : 'var(--chart-6)' }}
                      aria-hidden
                    />
                    <span className="text-muted">{item.name}</span>
                    <span className="ml-auto font-medium tabular-nums">{formatCompact(item.value)}</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <EmptyState kind="products" title="No availability data" />
          )}
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader
            title="Price change activity"
            subtitle="Daily increases and decreases detected by the pipeline"
            icon={<Activity className="h-4 w-4" />}
            action={
              <Link to="/changes" className="link text-xs">
                View all
              </Link>
            }
          />
          {priceChangeData.length ? (
            <BarSeries
              data={priceChangeData}
              xKey="date"
              bars={[
                { key: 'decreases', label: 'Decreases', color: 'var(--chart-3)' },
                { key: 'increases', label: 'Increases', color: 'var(--chart-5)' },
              ]}
              height={240}
              stacked
            />
          ) : (
            <EmptyState kind="price" title="No price changes recorded in this window" />
          )}
        </Card>

        <Card>
          <CardHeader
            title="Pipeline health"
            subtitle="Latest scheduled run"
            icon={<Gauge className="h-4 w-4" />}
            action={
              <Link to="/pipeline" className="link text-xs">
                Runs
              </Link>
            }
          />
          {latestRun.data?.run_id ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Badge tone={statusTone(latestRun.data.status)} dot>
                  {latestRun.data.status}
                </Badge>
                <span className="text-xs text-subtle">{formatRelative(latestRun.data.started_at)}</span>
              </div>
              <dl className="grid grid-cols-2 gap-2 text-xs">
                {[
                  ['Extracted', formatNumber(latestRun.data.records_extracted ?? 0)],
                  ['Loaded', formatNumber(latestRun.data.records_valid ?? 0)],
                  ['Merged duplicates', formatNumber(latestRun.data.duplicates_merged ?? 0)],
                  ['Price changes', formatNumber(latestRun.data.price_changes ?? 0)],
                  ['Duration', formatDuration(latestRun.data.duration_ms)],
                  ['DQ score', String(latestRun.data.dq_score ?? '—')],
                ].map(([label, value]) => (
                  <div key={label as string} className="rounded-lg border border-line bg-surface-2 px-2.5 py-2">
                    <dt className="text-[10px] uppercase tracking-wide text-subtle">{label}</dt>
                    <dd className="mt-0.5 font-medium tabular-nums">{value}</dd>
                  </div>
                ))}
              </dl>
              {latestRun.data.error_message ? (
                <p className="rounded-lg bg-warning-soft px-2.5 py-2 text-[11px] text-warning">
                  {String(latestRun.data.error_message).slice(0, 160)}
                </p>
              ) : null}
            </div>
          ) : (
            <EmptyState kind="activity" title="No runs recorded" message="Trigger a run from the Pipeline screen." />
          )}
        </Card>
      </div>

      {/* ------------------------------------------------------------- movers table */}
      <Card padded={false}>
        <div className="p-4 sm:p-5">
          <CardHeader
            title="Largest price movements"
            subtitle="Ordered by absolute percentage change"
            icon={<TrendingDown className="h-4 w-4" />}
            action={
              can('read') ? (
                <Link to="/changes" className="link text-xs">
                  Open change feed
                </Link>
              ) : null
            }
          />
        </div>
        <DataTable
          rows={movers.data ?? []}
          rowKey={(row: any, index) => `${row.product_id}-${index}`}
          emptyMessage="No significant price movement detected in this window"
          columns={[
            {
              key: 'product',
              header: 'Product',
              render: (row: any) => (
                <Link to={`/products/${row.product_id}`} className="block max-w-[22rem]">
                  <span className="block truncate font-medium text-ink">{row.canonical_name}</span>
                  <span className="block truncate text-xs text-subtle">{row.category_name ?? 'Uncategorised'}</span>
                </Link>
              ),
            },
            { key: 'source', header: 'Source', hideBelow: 'md', render: (row: any) => <Badge tone="neutral">{row.source_code}</Badge> },
            { key: 'from', header: 'From', align: 'right', hideBelow: 'sm', render: (row: any) => formatPrice(row.previous_price) },
            { key: 'to', header: 'To', align: 'right', render: (row: any) => formatPrice(row.new_price) },
            {
              key: 'change',
              header: 'Change',
              align: 'right',
              sortValue: (row: any) => row.change_pct,
              render: (row: any) => <DeltaPill value={row.change_pct} />,
            },
            {
              key: 'band',
              header: 'Band',
              align: 'center',
              hideBelow: 'lg',
              render: (row: any) => <Badge tone={statusTone(row.direction)}>{row.magnitude_band ?? '—'}</Badge>,
            },
            { key: 'date', header: 'Detected', align: 'right', hideBelow: 'md', render: (row: any) => formatDate(row.full_date) },
          ]}
          sort={{ by: 'change', dir: 'desc' }}
        />
      </Card>

      {/* ------------------------------------------------------------- quality strip */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Data quality posture"
            subtitle="Weighted score from the 12-rule framework"
            icon={<ShieldCheck className="h-4 w-4" />}
            action={
              <Link to="/quality" className="link text-xs">
                Details
              </Link>
            }
          />
          {quality.data?.rules?.length ? (
            <>
              <div className="mb-3 flex items-center gap-3">
                <div className="flex-1">
                  <div className="mb-1 flex items-center justify-between text-xs">
                    <span className="text-muted">Score</span>
                    <span className="font-semibold tabular-nums">{quality.data.score}</span>
                  </div>
                  <div className="h-2 w-full overflow-hidden rounded-full bg-surface-3">
                    <div
                      className={cn(
                        'h-full rounded-full',
                        quality.data.score >= 90 ? 'bg-success' : quality.data.score >= 75 ? 'bg-warning' : 'bg-danger',
                      )}
                      style={{ width: `${Math.min(100, quality.data.score)}%` }}
                    />
                  </div>
                </div>
                <div className="flex gap-1.5">
                  <Badge tone="success">{quality.data.pass} pass</Badge>
                  {quality.data.warn ? <Badge tone="warning">{quality.data.warn} warn</Badge> : null}
                  {quality.data.fail ? <Badge tone="danger">{quality.data.fail} fail</Badge> : null}
                </div>
              </div>
              <ul className="space-y-1">
                {quality.data.rules.slice(0, 5).map((rule: any) => (
                  <li key={rule.code} className="flex items-center gap-2 text-xs">
                    <span
                      className={cn(
                        'h-1.5 w-1.5 rounded-full',
                        rule.status === 'pass' ? 'bg-success' : rule.status === 'warn' ? 'bg-warning' : 'bg-danger',
                      )}
                      aria-hidden
                    />
                    <span className="font-mono text-[10px] text-subtle">{rule.code}</span>
                    <span className="truncate text-muted">{rule.name}</span>
                    <span className="ml-auto shrink-0 tabular-nums text-subtle">{rule.observed_value ?? '—'}</span>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <EmptyState kind="shield" title="No quality report yet" message="Run the pipeline to evaluate the rules." />
          )}
        </Card>

        <Card>
          <CardHeader
            title="Change summary"
            subtitle={`Last ${days} days`}
            icon={<Clock className="h-4 w-4" />}
          />
          {changeSummary.data ? (
            <div className="grid grid-cols-2 gap-2">
              {[
                ['New', changeSummary.data.new_products, 'success'],
                ['Removed', changeSummary.data.removed_products, 'danger'],
                ['Recurring', changeSummary.data.recurring, 'info'],
                ['Recategorised', changeSummary.data.category_changes, 'warning'],
                ['Total events', changeSummary.data.total_events, 'neutral'],
                ['Avg |change|', formatPercent(priceTrend.data?.[0]?.avg_abs_change_pct ?? null), 'brand'],
              ].map(([label, value, tone]) => (
                <div key={label as string} className="rounded-lg border border-line bg-surface-2 px-3 py-2">
                  <p className="text-[10px] uppercase tracking-wide text-subtle">{label}</p>
                  <p className={cn('mt-0.5 text-lg font-semibold tabular-nums', tone === 'success' && 'text-success', tone === 'danger' && 'text-danger')}>
                    {typeof value === 'number' ? formatNumber(value) : (value as string)}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <LoadingState label="Loading change summary…" rows={2} />
          )}
          {changeSummary.data && Number(changeSummary.data.total_events ?? 0) === 0 ? (
            <p className="mt-3 flex items-center gap-2 text-xs text-subtle">
              <AlertTriangle className="h-3.5 w-3.5" aria-hidden /> No lifecycle events in this window.
            </p>
          ) : null}
        </Card>
      </div>

      <LineTrend
        data={trendData}
        xKey="date"
        series={[{ key: 'avg_rating', label: 'Average rating' }]}
        height={200}
        formatY="number"
      />
    </div>
  )
}