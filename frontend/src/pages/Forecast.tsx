/**
 * Forecast screen: model accuracy, anomalies across the catalogue, seasonality and
 * per-product projections.
 *
 * The accuracy panel is deliberately first. A forecast nobody has measured is a guess,
 * and showing the mean and median backtest MAPE (with the worst cases named) before
 * any projection is the honest ordering.
 */

import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Activity,
  AlertTriangle,
  Brain,
  CalendarRange,
  Gauge,
  LineChart,
  RefreshCw,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Zap,
} from 'lucide-react'

import {
  Badge,
  Button,
  Card,
  CardHeader,
  DataTable,
  EmptyState,
  KeyValue,
  LoadingState,
  ProgressBar,
  Segmented,
  Select,
  StatTile,
  Tabs,
  useToast,
} from '@/components/ui'
import { BarSeries, HeatmapStrip } from '@/components/charts'
import { ForecastChart, type ForecastPoint } from '@/components/ForecastChart'
import { endpoints } from '@/lib/api'
import { useApiQuery } from '@/hooks/useApi'
import { useJob } from '@/lib/stream'
import { useQueryClient } from '@tanstack/react-query'
import { formatDate, formatNumber, formatPrice } from '@/lib/format'
import { cn } from '@/lib/cn'

const HORIZONS = [
  { id: '7', label: '7 days' },
  { id: '14', label: '14 days' },
  { id: '30', label: '30 days' },
]

export default function Forecast() {
  const [tab, setTab] = useState('accuracy')
  const [horizon, setHorizon] = useState('14')
  const [threshold, setThreshold] = useState('3.5')
  const [selected, setSelected] = useState<number | null>(null)
  const [rebuildJob, setRebuildJob] = useState<string | null>(null)
  const toast = useToast()
  const queryClient = useQueryClient()

  const backtest = useApiQuery(['forecast-backtest'], () => endpoints.forecastBacktest({ limit: 60 }), {
    staleTime: 300_000,
  })
  const anomalies = useApiQuery(
    ['forecast-anomalies', threshold],
    () => endpoints.allAnomalies({ threshold: Number(threshold), limit: 100 }),
    { staleTime: 120_000 },
  )
  const products = useApiQuery(
    ['forecast-products'],
    () => endpoints.products({ page: 1, page_size: 100, is_active: true, sort_by: 'observation_count', sort_dir: 'desc' }),
    { staleTime: 300_000 },
  )

  const job = useJob(rebuildJob)
  const jobStatus = String(job.job?.status ?? '')
  const jobRunning = Boolean(job.job) && !['succeeded', 'failed', 'cancelled'].includes(jobStatus)

  // A rebuild writes new forecasts; refresh the panels once it lands, then stop
  // tracking that job so the effect does not re-fire on every render.
  useEffect(() => {
    if (!['succeeded', 'failed'].includes(jobStatus)) return
    void queryClient.invalidateQueries({ queryKey: ['forecast-backtest'] })
    setRebuildJob(null)
  }, [jobStatus, queryClient])

  // The accuracy distribution is the useful shape: one mean hides that a few products
  // are modelled badly.
  const accuracyBuckets = useMemo(() => {
    const rows = backtest.data?.evaluated ? (backtest.data.best as any[]) : []
    const worst = (backtest.data?.worst as any[]) ?? []
    const all = [...rows, ...worst].filter((row) => typeof row?.mape_pct === 'number')
    if (!all.length) return []
    const buckets = [
      { label: '<5%', max: 5 },
      { label: '5-10%', max: 10 },
      { label: '10-25%', max: 25 },
      { label: '25-50%', max: 50 },
      { label: '>50%', max: Infinity },
    ].map((bucket) => ({ ...bucket, count: 0 }))
    for (const row of all) {
      const found = buckets.find((bucket) => row.mape_pct < bucket.max)
      if (found) found.count += 1
    }
    return buckets.filter((bucket) => bucket.count > 0)
  }, [backtest.data])

  async function rebuild() {
    try {
      const response = await endpoints.rebuildForecasts(Number(horizon))
      setRebuildJob(response.job_key)
      toast.success('Forecast rebuild queued', response.job_key)
    } catch (error) {
      toast.error('Could not queue the rebuild', (error as Error).message)
    }
  }

  return (
    <div className="space-y-4">
      {/* --------------------------------------------------------------- header */}
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <CardHeader
              title="Forecasting & anomaly detection"
              subtitle="Damped Holt-Winters with a weekly seasonal profile, scored by a holdout backtest"
              icon={<Brain className="h-4 w-4" />}
            />
            <p className="mt-2 max-w-3xl text-xs leading-relaxed text-muted">
              Every projection below is a classical exponential-smoothing model rather than a black box, and
              every accuracy figure comes from a genuine holdout backtest rather than from the fit that produced
              the forecast. Where the model is not accurate enough for a given product, the backtest panel says so.
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <label className="text-[11px] text-subtle">
              <span className="mb-1 block">Horizon</span>
              <Segmented options={HORIZONS} value={horizon} onChange={setHorizon} />
            </label>
            <Button
              icon={<RefreshCw className={cn('h-4 w-4', jobRunning && 'animate-spin')} />}
              onClick={rebuild}
              disabled={Boolean(jobRunning)}
            >
              {jobRunning ? `Rebuilding ${job.job?.progress_pct ?? 0}%` : 'Rebuild all'}
            </Button>
          </div>
        </div>
        {job.job ? (
          <div className="mt-3 rounded-lg border border-line bg-surface-2 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
              <span className="font-medium text-ink">
                {String(job.job.job_key)} · {String(job.job.status)}
                {job.job.stage ? ` · ${String(job.job.stage)}` : ''}
              </span>
              <span className="text-subtle">{job.events.length} progress event(s)</span>
            </div>
            <ProgressBar value={Number(job.job.progress_pct ?? 0)} className="mt-2" />
            {job.events.length ? (
              <ul className="mt-2 max-h-32 space-y-1 overflow-auto text-[11px] text-muted">
                {job.events.slice(-8).map((event, index) => (
                  <li key={index} className="flex items-start gap-2">
                    <Badge tone={event.level === 'error' ? 'danger' : event.level === 'warning' ? 'warning' : 'neutral'}>
                      {String(event.level ?? 'info')}
                    </Badge>
                    <span className="min-w-0 truncate">{String(event.message ?? '')}</span>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
      </Card>

      {/* ---------------------------------------------------------------- tiles */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile
          label="Model"
          value="Holt-Winters"
          hint="damped trend, weekly"
          icon={<Brain className="h-4 w-4" />}
        />
        <StatTile
          label="Products modelled"
          value={formatNumber(backtest.data?.evaluated ?? 0)}
          hint="with enough history"
          icon={<Gauge className="h-4 w-4" />}
        />
        <StatTile
          label="Mean error"
          value={backtest.data?.mean_mape_pct !== null && backtest.data?.mean_mape_pct !== undefined
            ? `${backtest.data.mean_mape_pct.toFixed(1)}%`
            : '—'}
          hint="MAPE, holdout"
          tone={(backtest.data?.mean_mape_pct ?? 100) < 15 ? 'success' : 'warning'}
          icon={<LineChart className="h-4 w-4" />}
        />
        <StatTile
          label="Anomalies"
          value={formatNumber(anomalies.data?.total ?? 0)}
          hint={`beyond ${threshold} robust σ`}
          tone={anomalies.data?.total ? 'warning' : 'success'}
          icon={<AlertTriangle className="h-4 w-4" />}
        />
      </div>

      <Tabs
        tabs={[
          { id: 'accuracy', label: 'Model accuracy' },
          { id: 'anomalies', label: 'Anomalies', count: anomalies.data?.total },
          { id: 'projection', label: 'Product projection' },
        ]}
        active={tab}
        onChange={setTab}
      />

      {/* ============================================================ accuracy */}
      {tab === 'accuracy' ? (
        <div className="space-y-3">
          <Card>
            <CardHeader
              title="How accurate is the model?"
              subtitle="Holdout backtest across the catalogue"
              icon={<Gauge className="h-4 w-4" />}
            />
            {backtest.isLoading ? (
              <LoadingState label="Backtesting the model…" rows={3} />
            ) : backtest.data?.evaluated ? (
              <>
                <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                  <div>
                    <p className="stat-label mb-2">Error distribution</p>
                    <BarSeries
                      data={accuracyBuckets}
                      xKey="label"
                      bars={[{ key: 'count', label: 'Products', color: 'var(--chart-1)' }]}
                      formatY="number"
                      height={220}
                    />
                  </div>
                  <div>
                    <p className="stat-label mb-2">Summary</p>
                    <KeyValue
                      items={[
                        { label: 'Model', value: String(backtest.data.model) },
                        { label: 'Products evaluated', value: formatNumber(backtest.data.evaluated) },
                        { label: 'Mean MAPE', value: `${backtest.data.mean_mape_pct}%` },
                        { label: 'Median MAPE', value: `${backtest.data.median_mape_pct}%` },
                        { label: 'Horizon', value: `${backtest.data.horizon} days` },
                      ]}
                    />
                    <p className="mt-3 rounded-lg bg-surface-2 p-3 text-[11px] leading-relaxed text-muted">
                      {backtest.data.note} A mean alone would hide a poorly modelled tail, so the worst cases are
                      listed rather than averaged away.
                    </p>
                  </div>
                </div>
              </>
            ) : (
              <EmptyState
                icon={<Brain className="h-5 w-5" />}
                title="Not enough history yet"
                message="The model needs at least 21 observations per product before a backtest is meaningful."
              />
            )}
          </Card>

          {backtest.data?.evaluated ? (
            <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
              <Card>
                <CardHeader title="Most accurate products" subtitle="MAPE under 5%" icon={<TrendingUp className="h-4 w-4" />} />
                <DataTable
                  rows={(backtest.data.best as any[]) ?? []}
                  rowKey={(row: any) => String(row.product_id)}
                  maxHeight={280}
                  columns={[
                    {
                      key: 'name',
                      header: 'Product',
                      render: (row: any) => (
                        <span className="block max-w-[16rem] truncate">{row.name ?? `#${row.product_id}`}</span>
                      ),
                    },
                    { key: 'observations', header: 'Obs', align: 'right', render: (row: any) => formatNumber(row.observations) },
                    {
                      key: 'mape_pct',
                      header: 'MAPE',
                      align: 'right',
                      render: (row: any) => <Badge tone="success">{row.mape_pct.toFixed(2)}%</Badge>,
                    },
                  ]}
                />
              </Card>
              <Card>
                <CardHeader title="Least accurate products" subtitle="Treat these with caution" icon={<TrendingDown className="h-4 w-4" />} />
                <DataTable
                  rows={(backtest.data.worst as any[]) ?? []}
                  rowKey={(row: any) => String(row.product_id)}
                  maxHeight={280}
                  columns={[
                    {
                      key: 'name',
                      header: 'Product',
                      render: (row: any) => (
                        <span className="block max-w-[16rem] truncate">{row.name ?? `#${row.product_id}`}</span>
                      ),
                    },
                    { key: 'observations', header: 'Obs', align: 'right', render: (row: any) => formatNumber(row.observations) },
                    {
                      key: 'mape_pct',
                      header: 'MAPE',
                      align: 'right',
                      render: (row: any) => (
                        <Badge tone={row.mape_pct > 40 ? 'danger' : 'warning'}>{row.mape_pct.toFixed(2)}%</Badge>
                      ),
                    },
                  ]}
                />
              </Card>
            </div>
          ) : null}
        </div>
      ) : null}

      {/* =========================================================== anomalies */}
      {tab === 'anomalies' ? (
        <div className="space-y-3">
          <Card>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <CardHeader
                title="Anomalous price observations"
                subtitle="Robust z-score against a centred rolling median"
                icon={<AlertTriangle className="h-4 w-4" />}
              />
              <label className="flex items-center gap-2 text-[11px] text-subtle">
                Threshold (σ)
                <Select value={threshold} onChange={(event) => setThreshold(event.target.value)} className="h-8 w-24">
                  {['2.5', '3.5', '5', '8'].map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </Select>
              </label>
            </div>

            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <StatTile label="Total" value={formatNumber(anomalies.data?.total ?? 0)} />
              <StatTile label="Spikes" value={formatNumber(anomalies.data?.by_direction?.spike ?? 0)} tone="warning" />
              <StatTile label="Drops" value={formatNumber(anomalies.data?.by_direction?.drop ?? 0)} tone="info" />
              <StatTile label="Critical" value={formatNumber(anomalies.data?.by_severity?.critical ?? 0)} tone="danger" />
            </div>

            <p className="mt-3 rounded-lg bg-surface-2 p-3 text-[11px] leading-relaxed text-muted">
              The detector uses the median absolute deviation rather than a standard deviation, because a single
              scraping defect — a price parsed as 1000× the real one — would inflate a standard deviation and thereby
              mask itself. Median-based scoring is not fooled by the very errors this pipeline exists to catch.
            </p>
          </Card>

          <Card>
            {anomalies.isLoading ? (
              <LoadingState label="Scanning for anomalies…" rows={5} />
            ) : anomalies.data?.anomalies?.length ? (
              <DataTable
                rows={anomalies.data.anomalies as any[]}
                rowKey={(row: any, index) => `${row.product_id}-${row.date}-${index}`}
                maxHeight={520}
                columns={[
                  {
                    key: 'product_id',
                    header: 'Product',
                    render: (row: any) => (
                      <Link to={`/products/${row.product_id}`} className="font-medium hover:underline">
                        #{row.product_id}
                      </Link>
                    ),
                  },
                  { key: 'date', header: 'Date', render: (row: any) => formatDate(row.date) },
                  {
                    key: 'value',
                    header: 'Observed',
                    align: 'right',
                    render: (row: any) => formatPrice(row.value),
                  },
                  {
                    key: 'expected',
                    header: 'Expected',
                    align: 'right',
                    render: (row: any) => formatPrice(row.expected),
                  },
                  {
                    key: 'score',
                    header: 'Score',
                    align: 'right',
                    render: (row: any) => (
                      <span className={cn('font-medium', row.score > 0 ? 'text-warning' : 'text-info')}>
                        {row.score > 0 ? '+' : ''}
                        {Number(row.score).toFixed(1)}σ
                      </span>
                    ),
                  },
                  {
                    key: 'direction',
                    header: 'Direction',
                    render: (row: any) => (
                      <Badge tone={row.direction === 'spike' ? 'warning' : 'info'}>{row.direction}</Badge>
                    ),
                  },
                  {
                    key: 'severity',
                    header: 'Severity',
                    render: (row: any) => (
                      <Badge
                        tone={
                          row.severity === 'critical' ? 'danger' : row.severity === 'high' ? 'warning' : 'neutral'
                        }
                      >
                        {row.severity}
                      </Badge>
                    ),
                  },
                ]}
              />
            ) : (
              <EmptyState
                icon={<Sparkles className="h-5 w-5" />}
                title="No anomalies at this threshold"
                message="Every observed price sits within the threshold of its local median. Lower it to be more sensitive."
              />
            )}
          </Card>
        </div>
      ) : null}

      {/* =========================================================== projection */}
      {tab === 'projection' ? (
        <ProductProjection
          products={(products.data?.items ?? []) as any[]}
          selected={selected}
          onSelect={setSelected}
          horizon={Number(horizon)}
        />
      ) : null}
    </div>
  )
}

/* =====================================================================================
   Per-product projection
   ===================================================================================== */
function ProductProjection({
  products,
  selected,
  onSelect,
  horizon,
}: {
  products: any[]
  selected: number | null
  onSelect: (id: number) => void
  horizon: number
}) {
  const productId = selected ?? products[0]?.product_id ?? null

  const history = useApiQuery(
    ['forecast-history', productId],
    () => (productId ? endpoints.productHistory(productId, 400) : Promise.resolve([])),
    { enabled: Boolean(productId), staleTime: 300_000 },
  )
  const forecast = useApiQuery(
    ['forecast', productId, horizon],
    () => (productId ? endpoints.forecast(productId, horizon) : Promise.resolve(null)),
    { enabled: Boolean(productId), staleTime: 300_000 },
  )
  const advice = useApiQuery(
    ['forecast-advice', productId, horizon],
    () => (productId ? endpoints.predictPrice(productId, horizon) : Promise.resolve(null)),
    { enabled: Boolean(productId), staleTime: 300_000 },
  )
  const seasonal = useApiQuery(
    ['forecast-seasonal', productId],
    () => (productId ? endpoints.seasonality(productId) : Promise.resolve(null)),
    { enabled: Boolean(productId), staleTime: 300_000 },
  )

  if (!products.length) {
    return (
      <Card>
        <EmptyState icon={<Activity className="h-5 w-5" />} title="No products to project" message="Run the pipeline first." />
      </Card>
    )
  }

  const forecastPoints = ((forecast.data?.points ?? []) as ForecastPoint[]) ?? []
  const historyRows = ((history.data ?? []) as any[]).map((row) => ({
    date: String(row.full_date ?? row.date ?? ''),
    value: row.price_usd ?? row.new_price_usd ?? null,
  }))

  return (
    <div className="space-y-3">
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardHeader
            title="Product projection"
            subtitle="History, forecast and a confidence band"
            icon={<CalendarRange className="h-4 w-4" />}
          />
          <label className="flex items-center gap-2 text-[11px] text-subtle">
            Product
            <Select
              value={productId ? String(productId) : ''}
              onChange={(event) => onSelect(Number(event.target.value))}
              className="h-8 w-64"
            >
              {products.map((product) => (
                <option key={product.product_id} value={product.product_id}>
                  {product.canonical_name}
                </option>
              ))}
            </Select>
          </label>
        </div>

        {forecast.isLoading ? (
          <LoadingState label="Fitting the model…" rows={4} />
        ) : forecast.data?.reason ? (
          <EmptyState
            icon={<Brain className="h-5 w-5" />}
            title="No forecast for this product"
            message={String(forecast.data.reason)}
          />
        ) : (
          <>
            <ForecastChart history={historyRows} forecast={forecastPoints} height={320} />
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <StatTile
                label="Backtest MAPE"
                value={
                  forecast.data?.mape_pct !== null && forecast.data?.mape_pct !== undefined
                    ? `${forecast.data.mape_pct.toFixed(2)}%`
                    : '—'
                }
                hint="holdout, not fit"
                tone={(forecast.data?.mape_pct ?? 100) < 15 ? 'success' : 'warning'}
              />
              <StatTile label="Observations" value={formatNumber(forecast.data?.observations ?? 0)} />
              <StatTile
                label="Trend / year"
                value={
                  forecast.data?.trend_pct_per_year !== null && forecast.data?.trend_pct_per_year !== undefined
                    ? `${forecast.data.trend_pct_per_year > 0 ? '+' : ''}${forecast.data.trend_pct_per_year.toFixed(1)}%`
                    : '—'
                }
                tone={(forecast.data?.trend_pct_per_year ?? 0) >= 0 ? 'success' : 'warning'}
              />
              <StatTile
                label="Forecast"
                value={formatPrice(forecastPoints[0]?.value)}
                hint={`${horizon}-day horizon`}
                tone="info"
              />
            </div>
          </>
        )}
      </Card>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <Card>
          <CardHeader title="Recommended price" subtitle="Damped at the margin break-even" icon={<Zap className="h-4 w-4" />} />
          {advice.isLoading ? (
            <LoadingState label="Working out a price…" rows={2} />
          ) : advice.data?.recommended_price ? (
            <>
              <div className="grid grid-cols-2 gap-3">
                <StatTile label="Current" value={formatPrice(advice.data.current_price)} />
                <StatTile label="Recommended" value={formatPrice(advice.data.recommended_price)} tone="info" />
              </div>
              <p className="mt-2 text-xs text-muted">
                {Number(advice.data.change_pct) > 0 ? '+' : ''}
                {advice.data.change_pct}% · confidence {(advice.data.confidence * 100).toFixed(0)}%
              </p>
              <div className="mt-3 rounded-lg bg-surface-2 p-3 text-[11px] leading-relaxed text-muted">
                <p className="mb-1 font-medium text-ink">How this was derived</p>
                <ul className="space-y-0.5">
                  {(advice.data.notes ?? []).map((note: string, index: number) => (
                    <li key={index}>· {note}</li>
                  ))}
                </ul>
              </div>
            </>
          ) : (
            <EmptyState
              icon={<Zap className="h-5 w-5" />}
              title="No recommendation"
              message={String(advice.data?.reason ?? 'Not enough history to model a price.')}
            />
          )}
        </Card>

        <Card>
          <CardHeader title="Weekly seasonality" subtitle="Average price by weekday" icon={<CalendarRange className="h-4 w-4" />} />
          {seasonal.isLoading ? (
            <LoadingState label="Building the weekly profile…" rows={3} />
          ) : seasonal.data?.weekdays?.length ? (
            <HeatmapStrip
              data={(seasonal.data.weekdays as any[]).map((day) => ({
                label: String(day.name).slice(0, 3),
                value: Number(day.mean),
              }))}
              valueKey="value"
              height={200}
            />
          ) : (
            <EmptyState icon={<CalendarRange className="h-5 w-5" />} title="Not enough history" />
          )}
        </Card>
      </div>
    </div>
  )
}