import { useMemo, useState } from 'react'
import {
  AlertTriangle,
  Boxes,
  Clock,
  ExternalLink,
  Globe,
  LayoutGrid,
  Rows3,
  ShieldCheck,
  Table as TableIcon,
} from 'lucide-react'

import {
  Badge,
  Button,
  Card,
  CardHeader,
  DataTable,
  EmptyState,
  ErrorState,
  KeyValue,
  LoadingState,
  Modal,
  ProgressBar,
  StatTile,
  Tabs,
  type Column,
  type Tone,
} from '@/components/ui'
import { cn } from '@/lib/cn'
import { endpoints } from '@/lib/api'
import { useApiQuery } from '@/hooks/useApi'
import { formatDateTime, formatDuration, formatNumber, formatPrice, formatRelative, statusTone, titleCase, truncate } from '@/lib/format'

const KIND_TONE: Record<string, Tone> = { api: 'info', scrape: 'warning', synthetic: 'neutral' }
const SYNC_TONE: Record<string, Tone> = {
  healthy: 'success',
  failing: 'danger',
  idle: 'neutral',
  disabled: 'neutral',
  unknown: 'neutral',
}

const COUNTERS: { key: string; label: string; tone: string }[] = [
  { key: 'fetched', label: 'Fetched', tone: 'text-brand-600 dark:text-brand-300' },
  { key: 'cached', label: 'Cached', tone: 'text-info' },
  { key: 'allowed', label: 'Allowed', tone: 'text-success' },
  { key: 'blocked', label: 'Blocked', tone: 'text-danger' },
  { key: 'errors', label: 'Errors', tone: 'text-warning' },
]

function syncTone(status?: string | null): Tone {
  if (!status) return 'neutral'
  return SYNC_TONE[status] ?? (statusTone(status) as Tone)
}

function successTone(rate?: number | null): 'success' | 'warning' | 'danger' {
  if (rate === null || rate === undefined) return 'warning'
  if (rate >= 95) return 'success'
  if (rate >= 75) return 'warning'
  return 'danger'
}

/* ------------------------------------------------------------------ source card */
function SourceCard({ row, onPreview }: { row: any; onPreview: (code: string) => void }) {
  const registry = row.registry ?? {}
  const rate = row.success_rate_pct === null || row.success_rate_pct === undefined ? null : Number(row.success_rate_pct)
  const failures = Number(row.consecutive_failures ?? 0)

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-ink" title={row.name}>
            {row.name ?? row.source_code}
          </p>
          <p className="mt-0.5 truncate font-mono text-[10px] text-subtle">{row.source_code}</p>
        </div>
        <div className="flex shrink-0 flex-wrap justify-end gap-1">
          <Badge tone={KIND_TONE[String(row.kind)] ?? 'neutral'}>{titleCase(row.kind)}</Badge>
          <Badge tone={row.enabled ? 'success' : 'neutral'} dot={row.enabled}>
            {row.enabled ? 'enabled' : 'disabled'}
          </Badge>
          <Badge tone={syncTone(row.sync_status)}>{titleCase(row.sync_status ?? 'unknown')}</Badge>
        </div>
      </div>

      {registry.description ? (
        <p className="line-clamp-2 text-xs leading-relaxed text-muted">{registry.description}</p>
      ) : null}

      <div className="flex flex-wrap items-center gap-1.5">
        {row.terms_allowed ? (
          <Badge tone="success">terms allowed</Badge>
        ) : (
          <Badge tone="danger">terms restricted</Badge>
        )}
        {registry.robots_respected === false ? <Badge tone="danger">robots ignored</Badge> : null}
        {registry.supports_paging ? <Badge tone="neutral">paged</Badge> : null}
        <Badge tone="neutral">
          {formatNumber(row.rate_limit_per_minute ?? 0)} req/min {'\u00b7'} {row.min_delay_seconds ?? 0}s delay
        </Badge>
      </div>

      <div>
        <div className="mb-1 flex items-center justify-between text-xs">
          <span className="text-muted">Success rate</span>
          <span className="font-semibold tabular-nums">{rate === null ? '\u2014' : `${rate.toFixed(1)}%`}</span>
        </div>
        <ProgressBar value={rate ?? 0} tone={successTone(rate)} />
        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-subtle">
          <span>{formatNumber(row.total_runs ?? 0)} runs</span>
          <span>{formatNumber(row.total_records ?? 0)} records</span>
          <span>{formatNumber(row.products_seen ?? 0)} products</span>
          <span>{formatDuration(Number(row.avg_duration_seconds ?? 0) * 1000)} avg</span>
        </div>
      </div>

      {failures > 0 ? (
        <p className="flex items-start gap-2 rounded-lg bg-danger-soft px-2.5 py-2 text-[11px] text-danger">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
          <span className="min-w-0">
            {failures} consecutive failure{failures === 1 ? '' : 's'}
            {row.sync_message ? ` \u2014 ${truncate(String(row.sync_message), 120)}` : ''}
          </span>
        </p>
      ) : null}

      <div className="mt-auto flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3">
        <span className="text-[11px] text-subtle">
          Last run <span className="font-medium text-muted" title={formatDateTime(row.last_run_at)}>
            {formatRelative(row.last_run_at)}
          </span>
        </span>
        <div className="flex items-center gap-1.5">
          {registry.terms_url ? (
            <a
              href={registry.terms_url}
              target="_blank"
              rel="noreferrer noopener"
              className="link inline-flex items-center gap-1 text-[11px]"
            >
              Terms
              <ExternalLink className="h-3 w-3" aria-hidden />
            </a>
          ) : null}
          <Button size="sm" variant="secondary" onClick={() => onPreview(row.source_code)}>
            Preview raw records
          </Button>
        </div>
      </div>
    </Card>
  )
}

/* ------------------------------------------------------------------ preview modal */
function SourcePreviewModal({ code, onClose }: { code: string | null; onClose: () => void }) {
  const preview = useApiQuery(['source-preview', code], () => endpoints.sourcePreview(code ?? '', 5), {
    enabled: Boolean(code),
    staleTime: 0,
    placeholderData: undefined,
  })
  const data = preview.data
  const records: any[] = data?.records ?? []

  const columns: Column<any>[] = [
    {
      key: 'canonical_name',
      header: 'Product',
      render: (row) => (
        <span className="block max-w-[18rem]">
          <span className="block truncate font-medium">{row.canonical_name || row.raw_name || '\u2014'}</span>
          {row.raw_name && row.raw_name !== row.canonical_name ? (
            <span className="block truncate text-[11px] text-subtle" title={row.raw_name}>
              raw: {row.raw_name}
            </span>
          ) : null}
        </span>
      ),
    },
    { key: 'category', header: 'Category', hideBelow: 'sm', render: (row) => <span className="text-xs text-muted">{row.category ?? '\u2014'}</span> },
    {
      key: 'price',
      header: 'Price',
      align: 'right',
      render: (row) => (
        <span className="tabular-nums">
          {formatPrice(row.price, row.currency ?? 'USD')}
          {row.price_usd !== null && row.price_usd !== undefined && row.currency !== 'USD' ? (
            <span className="block text-[11px] text-subtle">= {formatPrice(row.price_usd)}</span>
          ) : null}
        </span>
      ),
    },
    {
      key: 'rating',
      header: 'Rating',
      align: 'center',
      hideBelow: 'lg',
      render: (row) => <span className="tabular-nums">{row.rating === null || row.rating === undefined ? '\u2014' : Number(row.rating).toFixed(1)}</span>,
    },
    { key: 'availability', header: 'Stock', hideBelow: 'md', render: (row) => <Badge tone={statusTone(row.availability)}>{titleCase(row.availability)}</Badge> },
    {
      key: 'quality_flags',
      header: 'Quality flags',
      render: (row) => {
        const flags: string[] = Array.isArray(row.quality_flags) ? row.quality_flags : []
        if (!flags.length) return <span className="text-subtle">\u2014</span>
        return (
          <span className="flex flex-wrap gap-1">
            {flags.map((flag) => (
              <Badge key={flag} tone={flag.includes('missing') || flag.includes('invalid') ? 'danger' : 'warning'}>
                {titleCase(flag)}
              </Badge>
            ))}
          </span>
        )
      },
    },
    {
      key: 'valid',
      header: 'Valid',
      align: 'center',
      render: (row) =>
        row.is_valid ? (
          <Badge tone="success">yes</Badge>
        ) : (
          <Badge tone="danger" className="max-w-[10rem] truncate">
            {truncate(String(row.reject_reason ?? 'rejected'), 22)}
          </Badge>
        ),
    },
    {
      key: 'url',
      header: '',
      align: 'right',
      hideBelow: 'xl',
      render: (row) =>
        row.product_url ? (
          <a href={row.product_url} target="_blank" rel="noreferrer noopener" className="link text-xs">
            open
          </a>
        ) : (
          <span className="text-subtle">\u2014</span>
        ),
    },
  ]

  return (
    <Modal
      open={Boolean(code)}
      onClose={onClose}
      title={code ? `Raw records \u2014 ${code}` : 'Raw records'}
      description="Live fetch of a few records straight from the source, after the cleaning stage. Nothing is written to the warehouse."
      size="xl"
    >
      {preview.isError ? (
        <ErrorState
          title="Preview failed"
          message={(preview.error as Error)?.message ?? 'The source could not be reached.'}
          onRetry={() => preview.refetch()}
        />
      ) : preview.isLoading || !data ? (
        <LoadingState label={`Fetching records from ${code ?? 'the source'}\u2026`} rows={4} />
      ) : (
        <div className="space-y-3">
          <KeyValue
            columns={4}
            items={[
              { label: 'Requested', value: formatNumber(data.requested ?? 0) },
              { label: 'Returned', value: formatNumber(data.returned ?? 0) },
              { label: 'HTTP calls', value: formatNumber(data.http_calls ?? 0) },
              { label: 'Errors', value: <span className={cn(data.errors ? 'text-danger' : undefined)}>{formatNumber(data.errors ?? 0)}</span> },
            ]}
          />
          {records.length ? (
            <DataTable
              rows={records}
              rowKey={(row, index) => `${row.source_product_id ?? index}`}
              dense
              emptyMessage="The source returned no usable records."
              columns={columns}
            />
          ) : (
            <EmptyState
              title="No records returned"
              message="The source responded but produced nothing cleanable. Check its rate limit and terms configuration."
            />
          )}
        </div>
      )}
    </Modal>
  )
}

/* ------------------------------------------------------------------ page */
export default function Sources() {
  const [view, setView] = useState('cards')
  const [previewCode, setPreviewCode] = useState<string | null>(null)

  const status = useApiQuery(['pipeline-source-status'], endpoints.sourceStatus)
  const registry = useApiQuery(['sources'], endpoints.sources)
  const robots = useApiQuery(['sources-robots'], endpoints.sourceRobots, { staleTime: 60_000 })

  const merged = useMemo(() => {
    const definitions = new Map<string, any>((registry.data ?? []).map((row: any) => [row.code, row]))
    return (status.data ?? []).map((row: any) => ({ ...row, registry: definitions.get(row.source_code) ?? null }))
  }, [status.data, registry.data])

  const totals = useMemo(() => {
    const rows = merged
    const rates = rows
      .map((row: any) => row.success_rate_pct)
      .filter((value: unknown) => value !== null && value !== undefined)
      .map(Number)
    return {
      registered: (registry.data ?? []).length,
      enabled: rows.filter((row: any) => row.enabled).length,
      records: rows.reduce((sum: number, row: any) => sum + Number(row.total_records ?? 0), 0),
      success: rates.length ? rates.reduce((sum, value) => sum + value, 0) / rates.length : null,
      blocked: Number(robots.data?.stats?.blocked ?? 0),
      avgDuration: rows.length
        ? rows.reduce((sum: number, row: any) => sum + Number(row.avg_duration_seconds ?? 0), 0) / rows.length
        : 0,
    }
  }, [merged, registry.data, robots.data])

  const columns: Column<any>[] = [
    {
      key: 'source',
      header: 'Source',
      sortValue: (row) => row.name ?? row.source_code,
      render: (row) => (
        <span className="block max-w-[16rem]">
          <span className="block truncate font-medium text-ink">{row.name ?? row.source_code}</span>
          <span className="block truncate font-mono text-[10px] text-subtle">{row.source_code}</span>
        </span>
      ),
    },
    { key: 'kind', header: 'Kind', hideBelow: 'sm', render: (row) => <Badge tone={KIND_TONE[String(row.kind)] ?? 'neutral'}>{titleCase(row.kind)}</Badge> },
    {
      key: 'health',
      header: 'Health',
      width: '9rem',
      render: (row) => (
        <span className="block min-w-[7rem]">
          <span className="mb-1 flex items-center justify-between gap-2 text-[11px]">
            <span className="truncate text-subtle">{titleCase(row.sync_status ?? 'unknown')}</span>
            <span className="tabular-nums">
              {row.success_rate_pct === null || row.success_rate_pct === undefined
                ? '\u2014'
                : `${Number(row.success_rate_pct).toFixed(0)}%`}
            </span>
          </span>
          <ProgressBar
            value={Number(row.success_rate_pct ?? 0)}
            tone={successTone(row.success_rate_pct === null || row.success_rate_pct === undefined ? null : Number(row.success_rate_pct))}
          />
        </span>
      ),
    },
    {
      key: 'products',
      header: 'Products',
      align: 'right',
      sortValue: (row) => row.products_seen,
      render: (row) => formatNumber(row.products_seen ?? 0),
    },
    {
      key: 'records',
      header: 'Records',
      align: 'right',
      hideBelow: 'md',
      sortValue: (row) => row.total_records,
      render: (row) => formatNumber(row.total_records ?? 0),
    },
    {
      key: 'rate_limit',
      header: 'Rate limit',
      align: 'right',
      hideBelow: 'xl',
      render: (row) => <span className="tabular-nums text-muted">{formatNumber(row.rate_limit_per_minute ?? 0)}/min</span>,
    },
    {
      key: 'failures',
      header: 'Fails',
      align: 'center',
      hideBelow: 'lg',
      render: (row) => {
        const failures = Number(row.consecutive_failures ?? 0)
        return failures ? <Badge tone="danger">{failures}</Badge> : <span className="text-subtle">0</span>
      },
    },
    {
      key: 'last_run',
      header: 'Last run',
      align: 'right',
      sortValue: (row) => (row.last_run_at ? new Date(row.last_run_at).getTime() : 0),
      render: (row) => (
        <span className="text-xs text-muted" title={formatDateTime(row.last_run_at)}>
          {formatRelative(row.last_run_at)}
        </span>
      ),
    },
    {
      key: 'preview',
      header: '',
      align: 'right',
      hideBelow: 'lg',
      render: (row) => (
        <button
          onClick={(event) => {
            event.stopPropagation()
            setPreviewCode(row.source_code)
          }}
          className="link text-xs"
        >
          Preview
        </button>
      ),
    },
  ]

  if (status.isError && !status.data) {
    return <ErrorState message={(status.error as Error)?.message} onRetry={() => status.refetch()} />
  }
  if (status.isLoading && !status.data) {
    return <LoadingState label="Loading ingestion sources\u2026" rows={6} />
  }

  const stats = robots.data?.stats ?? {}
  const allowed = Number(stats.allowed ?? 0)
  const blocked = Number(stats.blocked ?? 0)
  const decided = allowed + blocked
  const respectsRobots = Boolean(registry.data?.length) && (registry.data ?? []).every((row: any) => row.robots_respected !== false)

  return (
    <div className="space-y-4">
      {/* --------------------------------------------------------- compliance */}
      <Card>
        <CardHeader
          title="Compliance posture"
          subtitle="robots.txt decisions, politeness cache and the terms registered with every source"
          icon={<ShieldCheck className="h-4 w-4" />}
          action={
            respectsRobots ? (
              <Badge tone="success" dot>
                robots.txt respected
              </Badge>
            ) : (
              <Badge tone="warning" dot>
                robots.txt not enforced
              </Badge>
            )
          }
        />
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <KeyValue
            columns={1}
            items={[
              {
                label: 'User agent',
                value: (
                  <span className="truncate font-mono text-xs" title={robots.data?.user_agent}>
                    {robots.data?.user_agent ?? '\u2014'}
                  </span>
                ),
              },
              {
                label: 'robots.txt cache TTL',
                value: robots.data?.ttl_seconds ? formatDuration(Number(robots.data.ttl_seconds) * 1000) : '\u2014',
              },
              {
                label: 'Sources allowed by terms',
                value: `${(registry.data ?? []).filter((row: any) => row.terms_allowed).length} / ${totals.registered}`,
              },
            ]}
          />

          <div className="lg:col-span-2">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
              {COUNTERS.map((counter) => (
                <div key={counter.label} className="rounded-lg border border-line bg-surface-2 px-3 py-2">
                  <p className="stat-label">{counter.label}</p>
                  <p className={cn('mt-0.5 text-lg font-semibold tabular-nums', counter.tone)}>
                    {formatNumber(Number(stats[counter.key] ?? 0))}
                  </p>
                </div>
              ))}
            </div>
            <div className="mt-3">
              <div className="mb-1 flex items-center justify-between text-xs">
                <span className="text-muted">Allowed versus blocked decisions</span>
                <span className="tabular-nums text-subtle">{formatNumber(decided)} total</span>
              </div>
              <ProgressBar value={decided ? (allowed / decided) * 100 : 0} tone={blocked && !allowed ? 'danger' : 'success'} />
              <p className="mt-1.5 text-[11px] text-subtle">
                {totals.blocked ? (
                  <>
                    <AlertTriangle className="mr-1 inline h-3 w-3 text-warning" aria-hidden />
                    {formatNumber(totals.blocked)} request{totals.blocked === 1 ? '' : 's'} were refused by robots.txt and never sent.
                  </>
                ) : (
                  'No request has been blocked by robots.txt so far.'
                )}
              </p>
            </div>
          </div>
        </div>
      </Card>

      {/* ------------------------------------------------------------- KPI cards */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Registered sources"
          value={formatNumber(totals.registered)}
          hint={`${totals.enabled} enabled for ingestion`}
          icon={<Boxes className="h-4 w-4" />}
        />
        <StatTile
          label="Records ingested"
          value={formatNumber(totals.records)}
          hint="cumulative across every source"
          icon={<TableIcon className="h-4 w-4" />}
          tone="info"
        />
        <StatTile
          label="Average success rate"
          value={totals.success === null ? '\u2014' : `${totals.success.toFixed(1)}%`}
          hint={`mean duration ${formatDuration(totals.avgDuration * 1000)}`}
          icon={<ShieldCheck className="h-4 w-4" />}
          tone={successTone(totals.success)}
        />
        <StatTile
          label="Refused by robots.txt"
          value={formatNumber(totals.blocked)}
          hint="requests never sent upstream"
          icon={<Globe className="h-4 w-4" />}
          tone={totals.blocked ? 'warning' : 'success'}
        />
      </div>

      {/* ------------------------------------------------------------- sources */}
      <div className="space-y-3">
        <Tabs
          active={view}
          onChange={setView}
          tabs={[
            { id: 'cards', label: 'Cards', count: merged.length, icon: <LayoutGrid className="h-4 w-4" /> },
            { id: 'table', label: 'Table', count: merged.length, icon: <Rows3 className="h-4 w-4" /> },
          ]}
        />

        {status.isError ? (
          <ErrorState message={(status.error as Error)?.message} onRetry={() => status.refetch()} />
        ) : !merged.length ? (
          <Card>
            <EmptyState
              title="No ingestion source is registered"
              message="The source registry is empty, so no run can collect products."
              icon={<Boxes className="h-8 w-8" />}
            />
          </Card>
        ) : view === 'cards' ? (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 2xl:grid-cols-3">
            {merged.map((row: any) => (
              <SourceCard key={row.source_code} row={row} onPreview={setPreviewCode} />
            ))}
          </div>
        ) : (
          <Card padded={false}>
            <div className="p-4 sm:p-5">
              <CardHeader
                title="Source health"
                subtitle="Ingestion volume, success rate and sync state side by side"
                icon={<Boxes className="h-4 w-4" />}
                action={
                  <span className="flex items-center gap-1 text-[11px] text-subtle">
                    <Clock className="h-3.5 w-3.5" aria-hidden />
                    mean {formatDuration(totals.avgDuration * 1000)}
                  </span>
                }
              />
            </div>
            <DataTable
              rows={merged}
              rowKey={(row: any) => row.source_code}
              loading={status.isFetching}
              onRowClick={(row) => setPreviewCode(row.source_code)}
              emptyMessage="No source has reported yet"
              columns={columns}
            />
          </Card>
        )}
      </div>

      <SourcePreviewModal code={previewCode} onClose={() => setPreviewCode(null)} />
    </div>
  )
}
