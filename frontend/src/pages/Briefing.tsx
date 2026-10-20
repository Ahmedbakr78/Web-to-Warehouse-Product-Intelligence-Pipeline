/**
 * Morning briefing - the "what changed and what should I do" screen.
 *
 * The API composes existing analytics services into a ranked action queue, so
 * this screen never invents a metric. Every card links to the screen where the
 * user can act, and the whole page is exportable as JSON for a stand-up note.
 */

import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Brain,
  Check,
  CircleAlert,
  ClipboardCopy,
  Download,
  Gauge,
  Package,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Star,
  Tag,
  Timer,
  TrendingDown,
  TrendingUp,
  Zap,
} from 'lucide-react'

import {
  Badge,
  Button,
  Card,
  CardHeader,
  DeltaPill,
  EmptyState,
  ErrorState,
  LoadingState,
  Segmented,
  StatTile,
  useToast,
} from '@/components/ui'
import { cn } from '@/lib/cn'
import { endpoints } from '@/lib/api'
import { useApiQuery } from '@/hooks/useApi'
import { downloadJson, formatCompact, formatNumber, formatPrice, formatRelative } from '@/lib/format'

type Insight = {
  id: string
  kind: string
  severity: 'critical' | 'high' | 'medium' | 'low'
  title: string
  detail: string
  metric: string
  delta: number | null
  icon: string
  link: string
  action: string
}

type Briefing = {
  generated_at: string
  window_days: number
  headline: {
    observations: number
    canonical_products: number
    sources_reporting: number
    avg_price_usd: number | null
    price_changes: number
    significant_changes: number
    new_products: number
    removed_products: number
    quality_score: number | null
    opportunities: number
    risks: number
  }
  opportunities: Insight[]
  risks: Insight[]
  category_signals: Insight[]
  freshness: {
    sources: number
    healthy_sources: number
    stale_sources: number
    stale: Array<{ source_code: string; products: number; stale_pct: number | null; last_seen_at: string }>
  }
  best_value: Array<{
    product_id: number
    name: string
    price_usd: number | null
    rating: number | null
    value_score: number | null
    source_code: string
  }>
  actions: Insight[]
}

const WINDOWS = [
  { id: '7', label: '7d' },
  { id: '30', label: '30d' },
  { id: '90', label: '90d' },
  { id: '180', label: '180d' },
]

const SEVERITY_TONE = {
  critical: 'danger',
  high: 'warning',
  medium: 'info',
  low: 'neutral',
} as const

function InsightIcon({ name, className }: { name: string; className?: string }) {
  const icons: Record<string, typeof TrendingDown> = {
    'trending-down': TrendingDown,
    'trending-up': TrendingUp,
    activity: Gauge,
    tag: Tag,
    package: Package,
    scan: CircleAlert,
    shield: ShieldCheck,
    timer: Timer,
    compare: Sparkles,
  }
  const Icon = icons[name] ?? Sparkles
  return <Icon className={className} aria-hidden />
}

export default function BriefingPage() {
  const [days, setDays] = useState('30')
  const [filter, setFilter] = useState<'all' | 'opportunity' | 'risk'>('all')
  const toast = useToast()
  const query = useApiQuery(['intelligence-briefing', days], () => endpoints.briefing(Number(days), 6), {
    staleTime: 60_000,
  })

  const data = query.data as Briefing | undefined

  const items = useMemo(() => {
    if (!data) return []
    if (filter === 'opportunity') return data.opportunities
    if (filter === 'risk') return data.risks
    return data.actions
  }, [data, filter])

  if (query.isError) {
    return <ErrorState message={(query.error as Error)?.message} onRetry={() => query.refetch()} />
  }
  if (query.isLoading && !data) return <LoadingState label="Building today's briefing…" rows={6} />

  const headline = data?.headline
  const summary =
    headline && data
      ? `${formatNumber(headline.opportunities)} opportunities and ${formatNumber(headline.risks)} risks across ` +
        `${formatCompact(headline.observations)} observations from ${headline.sources_reporting} sources.`
      : ''

  function exportBriefing() {
    if (!data) return
    downloadJson(`briefing-${days}d.json`, { exported_at: new Date().toISOString(), ...data })
    toast.success('Briefing exported', `briefing-${days}d.json`)
  }

  async function copySummary() {
    const lines = [
      `Morning briefing · last ${days} days`,
      summary,
      '',
      ...(data?.actions ?? []).slice(0, 8).map((item, index) => `${index + 1}. ${item.title} — ${item.metric} (${item.action})`),
    ]
    try {
      await navigator.clipboard.writeText(lines.join('\n'))
      toast.success('Copied', 'The action queue is on your clipboard.')
    } catch {
      toast.error('Clipboard unavailable', 'Use Export JSON instead.')
    }
  }

  return (
    <div className="space-y-3 sm:space-y-4">
      {/* ------------------------------------------------------------- hero */}
      <Card className="relative overflow-hidden">
        <div
          className="pointer-events-none absolute inset-0 opacity-60"
          style={{
            background:
              'radial-gradient(50% 70% at 0% 0%, color-mix(in srgb, var(--chart-1) 18%, transparent), transparent 70%), radial-gradient(40% 60% at 100% 100%, color-mix(in srgb, var(--chart-2) 14%, transparent), transparent 70%)',
          }}
          aria-hidden
        />
        <div className="relative flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-600 text-white shadow-sm">
                <Brain className="h-5 w-5" aria-hidden />
              </span>
              <div>
                <h2 className="text-lg font-semibold tracking-tight text-ink">Morning briefing</h2>
                <p className="text-xs text-subtle">
                  {data ? `Generated ${formatRelative(data.generated_at)} · last ${days} days` : 'Reading the warehouse…'}
                </p>
              </div>
              <Badge tone="brand">action queue</Badge>
            </div>
            <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted">
              {summary || 'Prioritised opportunities, risks and category signals from the analytical warehouse.'}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Segmented options={WINDOWS} value={days} onChange={setDays} size="sm" />
            <Button size="sm" variant="secondary" icon={<ClipboardCopy className="h-4 w-4" />} onClick={copySummary}>
              Copy
            </Button>
            <Button size="sm" variant="secondary" icon={<Download className="h-4 w-4" />} onClick={exportBriefing}>
              Export
            </Button>
            <Button
              size="sm"
              variant="ghost"
              icon={<RefreshCw className={cn('h-4 w-4', query.isFetching && 'animate-spin')} />}
              onClick={() => query.refetch()}
            >
              Refresh
            </Button>
          </div>
        </div>
      </Card>

      {/* ------------------------------------------------------------- KPIs */}
      <div className="grid grid-cols-2 gap-2 sm:gap-3 lg:grid-cols-3 2xl:grid-cols-6">
        <StatTile
          label="Opportunities"
          value={headline ? formatNumber(headline.opportunities) : '—'}
          hint="price drops, gaps, discounts"
          icon={<TrendingDown className="h-4 w-4" />}
          tone="success"
        />
        <StatTile
          label="Risks"
          value={headline ? formatNumber(headline.risks) : '—'}
          hint="rises, stockouts, anomalies"
          icon={<TrendingUp className="h-4 w-4" />}
          tone="warning"
        />
        <StatTile
          label="New arrivals"
          value={headline ? formatCompact(headline.new_products) : '—'}
          hint="in the selected window"
          icon={<Sparkles className="h-4 w-4" />}
          tone="info"
        />
        <StatTile
          label="Removed"
          value={headline ? formatCompact(headline.removed_products) : '—'}
          hint="delisted or out of circulation"
          icon={<Package className="h-4 w-4" />}
          tone="danger"
        />
        <StatTile
          label="Quality score"
          value={headline?.quality_score != null ? headline.quality_score.toFixed(1) : '—'}
          hint="weighted DQ rules"
          icon={<ShieldCheck className="h-4 w-4" />}
          tone={
            headline?.quality_score == null
              ? 'neutral'
              : headline.quality_score >= 90
                ? 'success'
                : headline.quality_score >= 75
                  ? 'warning'
                  : 'danger'
          }
        />
        <StatTile
          label="Sources live"
          value={headline ? formatNumber(headline.sources_reporting) : '—'}
          hint="reporting observations"
          icon={<Zap className="h-4 w-4" />}
          tone="brand"
        />
      </div>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        {/* ------------------------------------------------------- action queue */}
        <Card className="xl:col-span-2">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <CardHeader
              title="Today's action queue"
              subtitle="Ranked by severity, then by the size of the move"
              icon={<Sparkles className="h-4 w-4" />}
              className="mb-0"
            />
            <Segmented
              options={[
                { id: 'all', label: 'All' },
                { id: 'opportunity', label: `Opportunities ${data?.headline.opportunities ?? ''}` },
                { id: 'risk', label: `Risks ${data?.headline.risks ?? ''}` },
              ]}
              value={filter}
              onChange={(value) => setFilter(value as typeof filter)}
              size="sm"
            />
          </div>

          <div className="mt-3 divide-y divide-[var(--border)] overflow-hidden rounded-xl border border-line">
            {items.length ? (
              items.map((item) => (
                <Link
                  key={item.id}
                  to={item.link}
                  className="group flex items-start gap-3 p-3 transition-colors hover:bg-surface-2 sm:p-4"
                >
                  <span
                    className={cn(
                      'flex h-9 w-9 shrink-0 items-center justify-center rounded-lg',
                      item.severity === 'critical' || item.severity === 'high'
                        ? 'bg-danger-soft text-danger'
                        : item.severity === 'medium'
                          ? 'bg-warning-soft text-warning'
                          : 'bg-brand-100 text-brand-600 dark:bg-brand-500/15 dark:text-brand-300',
                    )}
                  >
                    <InsightIcon name={item.icon} className="h-4 w-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-1.5">
                      <span className="truncate text-sm font-semibold text-ink">{item.title}</span>
                      <Badge tone={SEVERITY_TONE[item.severity]}>{item.severity}</Badge>
                    </span>
                    <span className="mt-0.5 block text-xs leading-snug text-muted">{item.detail}</span>
                    <span className="mt-1 inline-flex items-center gap-1 text-[11px] font-medium text-brand-600 dark:text-brand-300">
                      {item.action}
                      <ArrowRight className="h-3 w-3 transition-transform group-hover:translate-x-0.5" aria-hidden />
                    </span>
                  </span>
                  <span className="flex shrink-0 flex-col items-end gap-1">
                    {item.delta != null ? <DeltaPill value={item.delta} /> : <Badge tone="neutral">{item.metric}</Badge>}
                    <span className="hidden text-[10px] uppercase tracking-wide text-subtle sm:block">{item.kind}</span>
                  </span>
                </Link>
              ))
            ) : (
              <EmptyState
                icon={<Check className="h-5 w-5" />}
                title="Nothing needs attention"
                message="No matching insights in this window. Widen the range or check back after the next run."
              />
            )}
          </div>
        </Card>

        {/* ------------------------------------------------------- side column */}
        <div className="space-y-3">
          <Card>
            <CardHeader
              title="Data freshness"
              subtitle={`${data?.freshness.healthy_sources ?? 0} healthy · ${data?.freshness.stale_sources ?? 0} stale`}
              icon={<Timer className="h-4 w-4" />}
            />
            <div className="space-y-2">
              {(data?.freshness.stale ?? []).slice(0, 4).map((source) => (
                <div key={source.source_code} className="flex items-center justify-between gap-2 rounded-lg bg-surface-3 px-3 py-2">
                  <div className="min-w-0">
                    <p className="truncate text-xs font-medium text-ink">{source.source_code}</p>
                    <p className="text-[10px] text-subtle">{formatNumber(source.products)} products</p>
                  </div>
                  <Badge tone={(source.stale_pct ?? 0) >= 75 ? 'danger' : 'warning'}>
                    {(source.stale_pct ?? 0).toFixed(0)}% stale
                  </Badge>
                </div>
              ))}
              {!data?.freshness.stale.length ? (
                <p className="rounded-lg bg-success-soft px-3 py-2 text-xs text-success">All active sources are fresh.</p>
              ) : null}
              <Link to="/sources" className="link inline-flex items-center gap-1 text-xs">
                Review source health <ArrowRight className="h-3 w-3" aria-hidden />
              </Link>
            </div>
          </Card>

          <Card>
            <CardHeader
              title="Best value picks"
              subtitle="Rating per dollar, voted listings only"
              icon={<Star className="h-4 w-4" />}
            />
            <div className="space-y-2">
              {(data?.best_value ?? []).slice(0, 4).map((item) => (
                <Link
                  key={item.product_id}
                  to={`/products/${item.product_id}`}
                  className="flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 hover:bg-surface-2"
                >
                  <div className="min-w-0">
                    <p className="truncate text-xs font-medium text-ink">{item.name}</p>
                    <p className="text-[10px] text-subtle">
                      {item.source_code} · {formatPrice(item.price_usd, 'USD')}
                    </p>
                  </div>
                  <Badge tone="success">{item.rating?.toFixed(1) ?? '—'}★</Badge>
                </Link>
              ))}
              {!data?.best_value.length ? <p className="text-xs text-subtle">No rated listings yet.</p> : null}
            </div>
          </Card>

          <Card>
            <CardHeader
              title="Category signals"
              subtitle="Where prices are moving fastest"
              icon={<Gauge className="h-4 w-4" />}
            />
            <div className="space-y-2">
              {(data?.category_signals ?? []).slice(0, 5).map((item) => (
                <Link
                  key={item.id}
                  to={item.link}
                  className="flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 hover:bg-surface-2"
                >
                  <div className="min-w-0">
                    <p className="truncate text-xs font-medium text-ink">{item.title}</p>
                    <p className="truncate text-[10px] text-subtle">{item.detail}</p>
                  </div>
                  <Badge tone="neutral">{item.metric}</Badge>
                </Link>
              ))}
              {!data?.category_signals.length ? <p className="text-xs text-subtle">No category moves yet.</p> : null}
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}
