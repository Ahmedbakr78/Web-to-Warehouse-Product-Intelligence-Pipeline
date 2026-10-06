/**
 * Audit: the application audit trail, a per-action summary and the outbound HTTP
 * log that proves the pipeline respected robots.txt, cache headers and rate limits.
 *
 * `robots_allowed = false` is a *blocked* request, not a failure of the crawler: the
 * pipeline refused to fetch a path that robots.txt disallows, which is the compliance
 * evidence this screen exists to surface.
 */

import { useEffect, useMemo, useState } from 'react'
import {
  Ban,
  Database,
  FileClock,
  Globe,
  HardDriveDownload,
  ListFilter,
  RefreshCw,
  Repeat,
  ShieldCheck,
  Timer,
  Zap,
} from 'lucide-react'

import {
  Badge,
  Button,
  Card,
  CardHeader,
  DataTable,
  EmptyState,
  ErrorState,
  LoadingState,
  Pagination,
  Segmented,
  Select,
  StatTile,
  Tabs,
  type Column,
  useToast,
} from '@/components/ui'
import { endpoints } from '@/lib/api'
import { useApiQuery } from '@/hooks/useApi'
import {
  formatBytes,
  formatDateTime,
  formatDuration,
  formatNumber,
  formatRelative,
  downloadCsv,
  statusTone,
  titleCase,
  toCsv,
  truncate,
} from '@/lib/format'

type AuditRow = {
  audit_id: number
  user_id: number | null
  user_email: string | null
  action: string
  entity_type: string | null
  entity_id: string | null
  status: string
  ip_address: string | null
  duration_ms: number | null
  created_at: string
}

type ActionRow = { action: string; count: number; last_seen: string }

type HttpRow = {
  log_id: number
  run_id: string | null
  source_code: string | null
  method: string
  url: string
  host: string | null
  status_code: number | null
  elapsed_ms: number | null
  response_bytes: number | null
  robots_allowed: boolean | null
  robots_rule: string | null
  from_cache: boolean
  retry_count: number
  error: string | null
  requested_at: string
}

type Compliance = {
  requests: number
  blocked_requests: number
  cached_requests: number
  retried_requests: number
  total_bytes: number
  avg_elapsed_ms: number
  max_elapsed_ms: number
  hosts: number
}

const RANGES = [
  { id: '7', label: '7d' },
  { id: '30', label: '30d' },
  { id: '90', label: '90d' },
  { id: '365', label: '1y' },
]

const HTTP_LIMITS = [50, 100, 200, 500]

export default function Audit() {
  const [days, setDays] = useState('30')
  const [tab, setTab] = useState('audit')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  const [sourceCode, setSourceCode] = useState('')
  const [httpLimit, setHttpLimit] = useState(200)
  const [sort, setSort] = useState<{ by?: string; dir: 'asc' | 'desc' }>({ by: 'created_at', dir: 'desc' })
  const toast = useToast()

  const windowDays = Number(days)

  const auditLog = useApiQuery<{ items?: AuditRow[]; total?: number }>(
    ['audit', page, pageSize, windowDays],
    () => endpoints.auditLog({ page, page_size: pageSize, days: windowDays }),
  )
  const actions = useApiQuery<ActionRow[]>(['audit-actions'], endpoints.auditActions, { staleTime: 300_000 })
  const httpLog = useApiQuery<HttpRow[]>(
    ['http-log', httpLimit, sourceCode],
    () => endpoints.httpLog(httpLimit, sourceCode || undefined),
    { staleTime: 30_000 },
  )
  const compliance = useApiQuery<Compliance>(['compliance', windowDays], () => endpoints.compliance(windowDays), { staleTime: 60_000 })

  useEffect(() => {
    setPage(1)
  }, [windowDays, pageSize])

  const auditRows = auditLog.data?.items ?? []
  const auditTotal = Number(auditLog.data?.total ?? 0)
  const httpRows = useMemo(() => httpLog.data ?? [], [httpLog.data])

  const summary = useMemo(
    () => [...(actions.data ?? [])].sort((left, right) => Number(right.count ?? 0) - Number(left.count ?? 0)),
    [actions.data],
  )

  const sourceOptions = useMemo(() => {
    const codes = new Set<string>()
    for (const row of httpRows) if (row.source_code) codes.add(row.source_code)
    if (sourceCode) codes.add(sourceCode)
    return [...codes].sort()
  }, [httpRows, sourceCode])

  const onSort = (key: string) => {
    setSort((current) => (current.by === key ? { by: key, dir: current.dir === 'asc' ? 'desc' : 'asc' } : { by: key, dir: 'desc' }))
  }

  const stats = compliance.data
  const blockedShare = stats && stats.requests ? (stats.blocked_requests / stats.requests) * 100 : 0
  const cachedShare = stats && stats.requests ? (stats.cached_requests / stats.requests) * 100 : 0

  const auditColumns: Column<AuditRow>[] = [
    {
      key: 'created_at',
      header: 'Timestamp',
      sortValue: (row) => new Date(row.created_at).getTime(),
      render: (row) => (
        <span className="whitespace-nowrap text-xs text-muted" title={formatDateTime(row.created_at)}>
          {formatDateTime(row.created_at)}
        </span>
      ),
    },
    {
      key: 'user',
      header: 'User',
      render: (row) =>
        row.user_email ? (
          <span className="max-w-[14rem] truncate text-ink">{row.user_email}</span>
        ) : (
          <span className="text-xs text-subtle">system / anonymous</span>
        ),
    },
    {
      key: 'action',
      header: 'Action',
      sortValue: (row) => row.action,
      render: (row) => (
        <span className="font-mono text-xs font-medium text-brand-700 dark:text-brand-300" title={row.action}>
          {row.action}
        </span>
      ),
    },
    {
      key: 'entity',
      header: 'Entity',
      hideBelow: 'md',
      render: (row) => (
        <span className="text-xs text-muted">
          {row.entity_type ? (
            <>
              {titleCase(row.entity_type)}
              {row.entity_id ? <span className="text-subtle"> #{row.entity_id}</span> : null}
            </>
          ) : (
            '—'
          )}
        </span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      align: 'center',
      sortValue: (row) => row.status,
      render: (row) => (
        <Badge tone={statusTone(row.status)} dot>
          {titleCase(row.status)}
        </Badge>
      ),
    },
    { key: 'ip', header: 'IP', hideBelow: 'lg', render: (row) => <span className="font-mono text-xs text-muted">{row.ip_address ?? '—'}</span> },
    {
      key: 'duration',
      header: 'Duration',
      align: 'right',
      hideBelow: 'sm',
      sortValue: (row) => Number(row.duration_ms ?? 0),
      render: (row) => <span className="tabular-nums text-xs">{formatDuration(row.duration_ms)}</span>,
    },
  ]

  const actionColumns: Column<ActionRow>[] = [
    {
      key: 'action',
      header: 'Action',
      sortValue: (row) => row.action,
      render: (row) => <span className="font-mono text-xs font-medium text-brand-700 dark:text-brand-300">{row.action}</span>,
    },
    {
      key: 'count',
      header: 'Occurrences',
      align: 'right',
      sortValue: (row) => Number(row.count ?? 0),
      render: (row) => <span className="font-medium tabular-nums">{formatNumber(row.count ?? 0)}</span>,
    },
    {
      key: 'last_seen',
      header: 'Last seen',
      align: 'right',
      sortValue: (row) => new Date(row.last_seen).getTime(),
      render: (row) => (
        <span className="text-xs text-muted" title={formatDateTime(row.last_seen)}>
          {formatRelative(row.last_seen)}
        </span>
      ),
    },
  ]

  const httpColumns: Column<HttpRow>[] = [
    {
      key: 'requested_at',
      header: 'Timestamp',
      sortValue: (row) => new Date(row.requested_at).getTime(),
      render: (row) => (
        <span className="whitespace-nowrap text-xs text-muted" title={formatDateTime(row.requested_at)}>
          {formatDateTime(row.requested_at)}
        </span>
      ),
    },
    { key: 'source', header: 'Source', render: (row) => <Badge tone="neutral">{row.source_code ?? '—'}</Badge> },
    { key: 'method', header: 'Method', render: (row) => <span className="font-mono text-[11px] text-muted">{row.method}</span> },
    {
      key: 'url',
      header: 'URL',
      render: (row) => (
        <span className="block max-w-[26rem] truncate font-mono text-[11px] text-ink" title={row.url}>
          {truncate(row.url, 90)}
        </span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      align: 'center',
      sortValue: (row) => Number(row.status_code ?? 0),
      render: (row) =>
        row.status_code === null ? (
          <span className="text-subtle">—</span>
        ) : (
          <Badge tone={statusTone(row.status_code >= 400 ? 'failed' : 'success')}>{row.status_code}</Badge>
        ),
    },
    {
      key: 'elapsed',
      header: 'Elapsed',
      align: 'right',
      hideBelow: 'md',
      sortValue: (row) => Number(row.elapsed_ms ?? 0),
      render: (row) => <span className="tabular-nums text-xs">{formatDuration(row.elapsed_ms)}</span>,
    },
    {
      key: 'bytes',
      header: 'Bytes',
      align: 'right',
      hideBelow: 'lg',
      render: (row) => <span className="tabular-nums text-xs">{row.response_bytes === null ? '—' : formatBytes(row.response_bytes)}</span>,
    },
    {
      key: 'robots',
      header: 'robots.txt',
      align: 'center',
      render: (row) =>
        row.robots_allowed === false ? (
          <Badge tone="danger">Blocked</Badge>
        ) : row.robots_allowed === true ? (
          <Badge tone="success">Allowed</Badge>
        ) : (
          <Badge tone="neutral">Not checked</Badge>
        ),
    },
    {
      key: 'rule',
      header: 'Matching rule',
      hideBelow: 'xl',
      render: (row) => <span className="font-mono text-[11px] text-subtle">{row.robots_rule ?? '—'}</span>,
    },
    {
      key: 'cache',
      header: 'Cache',
      align: 'center',
      hideBelow: 'lg',
      render: (row) =>
        row.from_cache ? (
          <Badge tone="info">Cached</Badge>
        ) : (
          <span className="text-xs text-subtle">fetched</span>
        ),
    },
    {
      key: 'retries',
      header: 'Retries',
      align: 'right',
      hideBelow: 'md',
      render: (row) =>
        Number(row.retry_count ?? 0) > 0 ? (
          <Badge tone="warning">{row.retry_count}</Badge>
        ) : (
          <span className="text-xs text-subtle">0</span>
        ),
    },
    {
      key: 'error',
      header: 'Error',
      hideBelow: 'xl',
      render: (row) =>
        row.error ? (
          <span className="block max-w-[16rem] truncate text-xs text-danger" title={row.error}>
            {row.error}
          </span>
        ) : (
          <span className="text-subtle">—</span>
        ),
    },
  ]

  return (
    <div className="space-y-4">
      {/* --------------------------------------------------------------- compliance KPIs */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <StatTile
          label="Outbound requests"
          value={formatNumber(stats?.requests ?? 0)}
          hint={`${formatBytes(stats?.total_bytes ?? 0)} transferred`}
          icon={<Globe className="h-4 w-4" />}
        />
        <StatTile
          label="Blocked by robots.txt"
          value={formatNumber(stats?.blocked_requests ?? 0)}
          hint={`${blockedShare.toFixed(1)}% of requests refused`}
          icon={<Ban className="h-4 w-4" />}
          tone={blockedShare > 0 ? 'warning' : 'neutral'}
        />
        <StatTile
          label="Served from cache"
          value={formatNumber(stats?.cached_requests ?? 0)}
          hint={`${cachedShare.toFixed(1)}% avoided a fetch`}
          icon={<HardDriveDownload className="h-4 w-4" />}
          tone="info"
        />
        <StatTile
          label="Retried"
          value={formatNumber(stats?.retried_requests ?? 0)}
          hint="transient failures retried"
          icon={<Repeat className="h-4 w-4" />}
          tone={Number(stats?.retried_requests ?? 0) > 0 ? 'warning' : 'neutral'}
        />
        <StatTile label="Distinct hosts" value={formatNumber(stats?.hosts ?? 0)} hint="domains contacted" icon={<Database className="h-4 w-4" />} tone="brand" />
        <StatTile
          label="Avg latency"
          value={formatDuration(stats?.avg_elapsed_ms ?? null)}
          hint={`max ${formatDuration(stats?.max_elapsed_ms ?? null)}`}
          icon={<Timer className="h-4 w-4" />}
          tone="success"
        />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="flex max-w-3xl items-start gap-2 text-xs text-subtle">
          <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" aria-hidden />
          <span>
            <span className="font-medium text-muted">robots_allowed = false</span> means the request was{' '}
            <span className="font-medium text-muted">blocked by robots.txt</span>: the pipeline deliberately refused a disallowed path
            instead of scraping it. Those rows are the compliance evidence that the crawler stayed within the permitted scope.
          </span>
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <Segmented options={RANGES} value={days} onChange={setDays} size="sm" />
          <Button
            size="sm"
            variant="ghost"
            icon={<RefreshCw className={httpLog.isFetching ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />}
            onClick={() => {
              void auditLog.refetch()
              void httpLog.refetch()
              void compliance.refetch()
            }}
          >
            Refresh
          </Button>
        </div>
      </div>

      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { id: 'audit', label: 'Application audit', count: auditTotal || undefined, icon: <FileClock className="h-4 w-4" /> },
          { id: 'actions', label: 'Actions summary', count: summary.length || undefined, icon: <ListFilter className="h-4 w-4" /> },
          { id: 'http', label: 'HTTP compliance log', count: httpRows.length || undefined, icon: <Zap className="h-4 w-4" /> },
        ]}
      />

      {/* --------------------------------------------------------------- application audit */}
      {tab === 'audit' ? (
        auditLog.isError ? (
          <ErrorState message={(auditLog.error as Error)?.message} onRetry={() => auditLog.refetch()} />
        ) : auditLog.isLoading && !auditLog.data ? (
          <LoadingState label="Loading audit trail…" rows={8} />
        ) : (
          <Card padded={false}>
            <div className="p-4 sm:p-5">
              <CardHeader
                title="Application audit trail"
                subtitle={`Every privileged action recorded in the last ${days} days`}
                icon={<FileClock className="h-4 w-4" />}
              />
            </div>
            <DataTable
              rows={auditRows}
              columns={auditColumns}
              rowKey={(row) => String(row.audit_id)}
              loading={auditLog.isFetching}
              sort={sort}
              onSort={onSort}
              emptyMessage={`No audited actions in the last ${days} days`}
            />
            <div className="px-4 pb-4 sm:px-5 sm:pb-5">
              <Pagination
                page={page}
                pageSize={pageSize}
                total={auditTotal}
                onPage={setPage}
                onPageSize={(size) => {
                  setPageSize(size)
                  setPage(1)
                }}
              />
            </div>
          </Card>
        )
      ) : null}

      {/* --------------------------------------------------------------- actions summary */}
      {tab === 'actions' ? (
        actions.isError ? (
          <ErrorState message={(actions.error as Error)?.message} onRetry={() => actions.refetch()} />
        ) : (
          <Card padded={false}>
            <div className="p-4 sm:p-5">
              <CardHeader
                title="Audited actions"
                subtitle="Grouped by action, most frequent first"
                icon={<ListFilter className="h-4 w-4" />}
              />
            </div>
            <DataTable
              rows={summary}
              columns={actionColumns}
              rowKey={(row) => row.action}
              loading={actions.isFetching}
              emptyMessage="No audited actions recorded yet"
            />
          </Card>
        )
      ) : null}

      {/* --------------------------------------------------------------- HTTP compliance log */}
      {tab === 'http' ? (
        httpLog.isError ? (
          <ErrorState message={(httpLog.error as Error)?.message} onRetry={() => httpLog.refetch()} />
        ) : httpLog.isLoading && !httpLog.data ? (
          <LoadingState label="Loading HTTP log…" rows={8} />
        ) : (
          <Card padded={false}>
            <div className="p-4 sm:p-5">
              <CardHeader
                title="Outbound HTTP log"
                subtitle="Robots decision, cache usage and retries for every request the pipeline made"
                icon={<Zap className="h-4 w-4" />}
                action={
                  <div className="flex flex-wrap items-center justify-end gap-2">
                    <Button
                      size="sm"
                      variant="ghost"
                      icon={<HardDriveDownload className="h-4 w-4" />}
                      disabled={!httpRows.length}
                      onClick={() => {
                        const body = httpRows.map((row: HttpRow) => [
                          row.requested_at ?? '',
                          row.source_code ?? '',
                          row.method ?? '',
                          row.url ?? '',
                          row.status_code ?? '',
                          row.robots_allowed === null || row.robots_allowed === undefined ? '' : String(row.robots_allowed),
                          row.from_cache ? 'yes' : 'no',
                          row.retry_count ?? 0,
                          row.elapsed_ms ?? '',
                        ])
                        downloadCsv('http-compliance-log.csv', toCsv(
                          ['when', 'source', 'method', 'url', 'status', 'robots_allowed', 'cached', 'retries', 'elapsed_ms'],
                          body,
                        ))
                        toast.success('HTTP log exported', `${body.length} rows saved as CSV.`)
                      }}
                    >
                      Export CSV
                    </Button>
                    <Select
                      value={sourceCode}
                      aria-label="Filter by source"
                      className="h-9 w-40 py-0 text-xs"
                      onChange={(event) => setSourceCode(event.target.value)}
                    >
                      <option value="">All sources</option>
                      {sourceOptions.map((code) => (
                        <option key={code} value={code}>
                          {code}
                        </option>
                      ))}
                    </Select>
                    <Select
                      value={String(httpLimit)}
                      aria-label="Rows to load"
                      className="h-9 w-28 py-0 text-xs"
                      onChange={(event) => setHttpLimit(Number(event.target.value))}
                    >
                      {HTTP_LIMITS.map((limit) => (
                        <option key={limit} value={limit}>
                          Last {limit}
                        </option>
                      ))}
                    </Select>
                  </div>
                }
              />
            </div>
            {httpRows.length === 0 ? (
              <EmptyState
                title="No HTTP requests logged"
                message="The crawler records every outbound request here once a pipeline run starts."
                icon={<Globe className="h-7 w-7" />}
              />
            ) : (
              <DataTable
                rows={httpRows}
                columns={httpColumns}
                rowKey={(row) => String(row.log_id)}
                loading={httpLog.isFetching}
                emptyMessage="No HTTP requests match this filter"
              />
            )}
          </Card>
        )
      ) : null}
    </div>
  )
}