import { useMemo, useState } from 'react'
import {
  AlertTriangle,
  Boxes,
  CheckCircle2,
  Clock,
  Gauge,
  ListTree,
  Play,
  RefreshCw,
  Server,
  Timer,
} from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { BarSeries } from '@/components/charts'
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
  Pagination,
  ProgressBar,
  Segmented,
  Select,
  StatTile,
  Tabs,
  Toggle,
  useToast,
} from '@/components/ui'
import { endpoints } from '@/lib/api'
import { useApiQuery } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { formatCompact, formatDateTime, formatDuration, formatNumber, formatRelative, statusTone, titleCase } from '@/lib/format'

const STATUS_FILTERS = [
  { id: '', label: 'All' },
  { id: 'success', label: 'Success' },
  { id: 'partial', label: 'Partial' },
  { id: 'failed', label: 'Failed' },
  { id: 'running', label: 'Running' },
]

export default function Pipeline() {
  const [tab, setTab] = useState('runs')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  const [status, setStatus] = useState('')
  const [selectedRun, setSelectedRun] = useState<string | null>(null)
  const [showTrigger, setShowTrigger] = useState(false)
  const [sources, setSources] = useState<string[]>([])
  const [limit, setLimit] = useState(50)
  const [database, setDatabase] = useState('postgres')
  const [skipDq, setSkipDq] = useState(false)
  const [skipCatalog, setSkipCatalog] = useState(false)
  const [strict, setStrict] = useState(false)
  const queryClient = useQueryClient()
  const toast = useToast()
  const { can } = useAuth()

  const params = useMemo(() => ({ page, page_size: pageSize, status: status || undefined }), [page, pageSize, status])
  const runs = useApiQuery(['runs', params], () => endpoints.runs(params))
  const latest = useApiQuery(['run-latest'], endpoints.runLatest)
  const stages = useApiQuery(['stages'], endpoints.stages)
  const schedule = useApiQuery(['schedule'], endpoints.schedule)
  const sourceStatus = useApiQuery(['source-status'], endpoints.sourceStatus)
  const sourceRegistry = useApiQuery(['sources-registry'], endpoints.sources, { staleTime: 300_000 })
  const runDetail = useApiQuery(['run', selectedRun], () => endpoints.run(selectedRun!), { enabled: Boolean(selectedRun) })

  const trigger = useMutation({
    mutationFn: () => endpoints.triggerRunSync({ sources, limit_per_source: limit, database, skip_dq: skipDq, skip_catalog: skipCatalog, strict, trigger: 'dashboard' }),
    onSuccess: (result: any) => {
      toast.success('Pipeline finished', `${result.status} · ${formatNumber(result.counters?.snapshots_inserted ?? 0)} snapshots`)
      setShowTrigger(false)
      void queryClient.invalidateQueries()
    },
    onError: (error: Error) => toast.error('Pipeline failed', error.message),
  })

  const runRows = runs.data?.items ?? []
  const totals = stages.data?.totals ?? {}
  const recentRuns = runs.data?.items ?? []

  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    recentRuns.forEach((run: any) => {
      counts[run.status] = (counts[run.status] ?? 0) + 1
    })
    return counts
  }, [recentRuns])

  const sourceHealth = sourceStatus.data ?? []
  const enabledSources = (sourceRegistry.data ?? []).filter((source: any) => source.enabled)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Tabs
          active={tab}
          onChange={setTab}
          tabs={[
            { id: 'runs', label: 'Runs', icon: <ListTree className="h-4 w-4" /> },
            { id: 'sources', label: 'Source health', icon: <Boxes className="h-4 w-4" /> },
            { id: 'schedule', label: 'Schedule', icon: <Clock className="h-4 w-4" /> },
          ]}
        />
        <div className="flex items-center gap-2">
          <Button size="sm" variant="ghost" icon={<RefreshCw className="h-4 w-4" />} onClick={() => void queryClient.invalidateQueries()}>
            Refresh
          </Button>
          {can('run_pipeline') ? (
            <Button size="sm" variant="primary" icon={<Play className="h-4 w-4" />} onClick={() => setShowTrigger(true)}>
              Run pipeline
            </Button>
          ) : null}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Total runs"
          value={formatCompact(totals.etl_run ?? 0)}
          hint={`${formatNumber(totals.fact_price_snapshot ?? 0)} snapshots loaded`}
          icon={<Gauge className="h-4 w-4" />}
        />
        <StatTile
          label="Last run status"
          value={latest.data?.status ? <Badge tone={statusTone(latest.data.status)} dot>{latest.data.status}</Badge> : '—'}
          hint={latest.data?.started_at ? formatRelative(latest.data.started_at) : 'no runs recorded'}
          icon={<CheckCircle2 className="h-4 w-4" />}
          tone={latest.data?.status === 'success' ? 'success' : 'warning'}
        />
        <StatTile
          label="Last duration"
          value={formatDuration(latest.data?.duration_ms ?? null)}
          hint={`extracted ${formatNumber(latest.data?.records_extracted ?? 0)} · merged ${formatNumber(latest.data?.duplicates_merged ?? 0)}`}
          icon={<Timer className="h-4 w-4" />}
          tone="info"
        />
        <StatTile
          label="DQ score (last run)"
          value={latest.data?.dq_score !== null && latest.data?.dq_score !== undefined ? String(latest.data.dq_score) : '—'}
          hint={`${formatNumber(latest.data?.dq_passed ?? 0)} pass · ${formatNumber(latest.data?.dq_failed ?? 0)} fail`}
          icon={<AlertTriangle className="h-4 w-4" />}
          tone={(latest.data?.dq_score ?? 0) >= 90 ? 'success' : 'warning'}
        />
      </div>

      {tab === 'runs' ? (
        <Card padded={false}>
          <div className="flex flex-wrap items-center gap-2 p-3">
            <Segmented options={STATUS_FILTERS} value={status} onChange={(value) => { setStatus(value); setPage(1) }} size="sm" />
            <div className="ml-auto text-xs text-subtle">{formatNumber(runs.data?.total ?? 0)} runs</div>
          </div>

          {runs.isError ? (
            <div className="p-4">
              <ErrorState message={(runs.error as Error)?.message} onRetry={() => runs.refetch()} />
            </div>
          ) : (
            <>
              <DataTable
                rows={runRows}
                rowKey={(row: any) => row.run_id}
                loading={runs.isFetching}
                emptyMessage="No pipeline runs recorded yet"
                onRowClick={(row: any) => setSelectedRun(row.run_id)}
                columns={[
                  {
                    key: 'run_id',
                    header: 'Run',
                    render: (row: any) => (
                      <span className="flex items-center gap-2">
                        <span className="font-mono text-xs">{row.run_id?.slice(0, 10)}</span>
                        <Badge tone={statusTone(row.status)} dot>
                          {row.status}
                        </Badge>
                      </span>
                    ),
                  },
                  { key: 'trigger', header: 'Trigger', hideBelow: 'md', render: (row: any) => <Badge tone="neutral">{titleCase(row.trigger ?? 'manual')}</Badge> },
                  { key: 'database', header: 'Target', hideBelow: 'lg', render: (row: any) => <Badge tone="info">{row.target_database}</Badge> },
                  { key: 'started', header: 'Started', render: (row: any) => <span title={formatDateTime(row.started_at)}>{formatRelative(row.started_at)}</span> },
                  { key: 'duration', header: 'Duration', align: 'right', render: (row: any) => formatDuration(row.duration_ms) },
                  { key: 'extracted', header: 'Extracted', align: 'right', render: (row: any) => formatNumber(row.records_extracted ?? 0) },
                  { key: 'loaded', header: 'Loaded', align: 'right', render: (row: any) => formatNumber(row.records_valid ?? 0) },
                  { key: 'yield', header: 'Yield', align: 'right', hideBelow: 'sm', render: (row: any) => `${row.yield_pct ?? 0}%` },
                  { key: 'merged', header: 'Merged', align: 'right', hideBelow: 'lg', render: (row: any) => formatNumber(row.duplicates_merged ?? 0) },
                  { key: 'changes', header: 'Changes', align: 'right', hideBelow: 'md', render: (row: any) => formatNumber(row.price_changes ?? 0) },
                  { key: 'catalog', header: 'Catalog', align: 'right', hideBelow: 'xl', render: (row: any) => formatNumber(row.catalog_matched ?? 0) },
                  {
                    key: 'dq',
                    header: 'DQ',
                    align: 'right',
                    render: (row: any) => (
                      <span className="inline-flex items-center gap-2">
                        <span className="w-10 text-right font-mono text-xs tabular-nums">{row.dq_score ?? '—'}</span>
                        <span className="h-1.5 w-12 overflow-hidden rounded-full bg-surface-3">
                          <span
                            className={
                              (row.dq_score ?? 0) >= 90 ? 'block h-full bg-success' : (row.dq_score ?? 0) >= 75 ? 'block h-full bg-warning' : 'block h-full bg-danger'
                            }
                            style={{ width: `${Math.min(100, Number(row.dq_score ?? 0))}%` }}
                          />
                        </span>
                      </span>
                    ),
                  },
                ]}
              />
              <div className="p-3">
                <Pagination page={page} pageSize={pageSize} total={runs.data?.total ?? 0} onPage={setPage} onPageSize={setPageSize} />
              </div>
            </>
          )}
        </Card>
      ) : null}

      {tab === 'sources' ? (
        <div className="space-y-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {sourceHealth.slice(0, 4).map((source: any) => (
              <Card key={source.source_code}>
                <div className="mb-2 flex items-center justify-between gap-2">
                  <p className="truncate font-mono text-xs">{source.source_code}</p>
                  <Badge tone={source.enabled ? 'success' : 'neutral'}>{source.enabled ? 'enabled' : 'disabled'}</Badge>
                </div>
                <div className="space-y-1.5 text-xs">
                  <div className="flex justify-between">
                    <span className="text-subtle">Success rate</span>
                    <span className="font-medium tabular-nums">{Number(source.success_rate_pct ?? 0).toFixed(1)}%</span>
                  </div>
                  <ProgressBar
                    value={Number(source.success_rate_pct ?? 0)}
                    tone={Number(source.success_rate_pct ?? 0) >= 90 ? 'success' : Number(source.success_rate_pct ?? 0) >= 60 ? 'warning' : 'danger'}
                  />
                  <div className="flex justify-between">
                    <span className="text-subtle">Runs</span>
                    <span className="tabular-nums">{formatNumber(source.total_runs ?? 0)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-subtle">Records</span>
                    <span className="tabular-nums">{formatCompact(source.total_records ?? 0)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-subtle">Duration</span>
                    <span className="tabular-nums">{formatDuration(Number((source.avg_duration_seconds ?? 0) * 1000))}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-subtle">Last run</span>
                    <span className="tabular-nums">{formatRelative(source.last_run_at)}</span>
                  </div>
                  {Number(source.consecutive_failures ?? 0) > 0 ? (
                    <Badge tone="danger">{source.consecutive_failures} consecutive failures</Badge>
                  ) : null}
                </div>
              </Card>
            ))}
          </div>

          <Card padded={false}>
            <div className="p-4 sm:p-5">
              <CardHeader title="All sources" subtitle="Throughput and reliability per registered source" icon={<Server className="h-4 w-4" />} />
            </div>
            <DataTable
              rows={sourceHealth}
              rowKey={(row: any) => row.source_code}
              loading={sourceStatus.isFetching}
              emptyMessage="No sources registered"
              columns={[
                { key: 'code', header: 'Source', render: (row: any) => (
                  <span className="block max-w-[18rem]">
                    <span className="block truncate font-mono text-xs">{row.source_code}</span>
                    <span className="block truncate text-[11px] text-subtle">{row.name}</span>
                  </span>
                ) },
                { key: 'kind', header: 'Kind', align: 'center', render: (row: any) => <Badge tone={row.kind === 'scrape' ? 'warning' : row.kind === 'synthetic' ? 'info' : 'neutral'}>{row.kind}</Badge> },
                { key: 'rate', header: 'Rate limit', align: 'right', hideBelow: 'md', render: (row: any) => `${row.rate_limit_per_minute}/min` },
                { key: 'delay', header: 'Delay', align: 'right', hideBelow: 'lg', render: (row: any) => `${row.min_delay_seconds ?? 0}s` },
                { key: 'runs', header: 'Runs', align: 'right', render: (row: any) => formatNumber(row.total_runs ?? 0) },
                { key: 'records', header: 'Records', align: 'right', sortValue: (row: any) => row.total_records, render: (row: any) => formatCompact(row.total_records ?? 0) },
                { key: 'products', header: 'Products', align: 'right', hideBelow: 'sm', render: (row: any) => formatCompact(row.products_seen ?? 0) },
                { key: 'success', header: 'Success', align: 'right', render: (row: any) => `${Number(row.success_rate_pct ?? 0).toFixed(0)}%` },
                { key: 'sync', header: 'Sync state', align: 'center', hideBelow: 'md', render: (row: any) => (
                  <Badge tone={statusTone(row.sync_status)}>{titleCase(row.sync_status ?? 'unknown')}</Badge>
                ) },
                { key: 'last', header: 'Last run', align: 'right', hideBelow: 'lg', render: (row: any) => formatRelative(row.last_run_at) },
              ]}
            />
          </Card>
        </div>
      ) : null}

      {tab === 'schedule' ? (
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
          <Card>
            <CardHeader title="Orchestration" subtitle="Airflow DAG configuration" icon={<Clock className="h-4 w-4" />} />
            {schedule.data ? (
              <KeyValue
                items={[
                  { label: 'DAG id', value: <span className="font-mono text-xs">{schedule.data.dag_id}</span> },
                  { label: 'Schedule (cron)', value: <span className="font-mono text-xs">{schedule.data.cron}</span> },
                  { label: 'Orchestrator', value: schedule.data.orchestrator },
                  { label: 'Last run', value: formatDateTime(schedule.data.last_run_at) },
                  { label: 'Next expected', value: formatDateTime(schedule.data.next_expected) },
                ]}
              />
            ) : (
              <LoadingState label="Loading schedule…" rows={2} />
            )}
            <p className="mt-4 rounded-lg bg-surface-2 p-3 text-[11px] leading-relaxed text-muted">
              The DAG runs pre-flight guards (database health, robots.txt compliance, source probe) before the ETL
              stages, then a data-quality gate that fails the run only on <strong>critical</strong> rule failures.
              Notifications are only published when the run actually produced changes.
            </p>
          </Card>

          <Card>
            <CardHeader title="Trigger mix" subtitle="How runs are started" icon={<Gauge className="h-4 w-4" />} />
            {(schedule.data?.trigger_mix ?? []).length ? (
              <BarSeries
                data={schedule.data.trigger_mix.map((item: any) => ({ name: titleCase(item.trigger), count: item.count }))}
                xKey="name"
                bars={[{ key: 'count', label: 'Runs' }]}
                height={240}
              />
            ) : (
              <EmptyState title="No trigger data" />
            )}
          </Card>

          <Card className="xl:col-span-2">
            <CardHeader title="Stage catalogue" subtitle="What each pipeline stage is responsible for" icon={<ListTree className="h-4 w-4" />} />
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {(stages.data?.stages ?? []).map((stage: string, index: number) => (
                <div key={stage} className="rounded-lg border border-line bg-surface-2 px-3 py-2">
                  <p className="font-mono text-xs font-medium">{stage}</p>
                  <p className="mt-0.5 text-[11px] text-subtle">{STAGE_DESCRIPTIONS[index] ?? ''}</p>
                </div>
              ))}
            </div>
            {Object.keys(statusCounts).length ? (
              <div className="mt-4">
                <p className="section-title mb-2">Recent run outcomes</p>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(statusCounts).map(([statusValue, count]) => (
                    <Badge key={statusValue} tone={statusTone(statusValue)}>
                      {statusValue}: {count}
                    </Badge>
                  ))}
                </div>
              </div>
            ) : null}
          </Card>
        </div>
      ) : null}

      {/* ------------------------------------------------------------- run detail drawer */}
      <Modal
        open={Boolean(selectedRun)}
        onClose={() => setSelectedRun(null)}
        title={runDetail.data?.run_id ? `Run ${runDetail.data.run_id.slice(0, 16)}…` : 'Run detail'}
        description={runDetail.data ? `${titleCase(runDetail.data.trigger)} · ${runDetail.data.target_database} · ${formatDateTime(runDetail.data.started_at)}` : undefined}
        size="xl"
      >
        {runDetail.isLoading ? (
          <LoadingState label="Loading run detail…" rows={4} />
        ) : runDetail.data ? (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={statusTone(runDetail.data.status)} dot>
                {runDetail.data.status}
              </Badge>
              {runDetail.data.dag_id ? <Badge tone="neutral">dag: {runDetail.data.dag_id}</Badge> : null}
              {runDetail.data.task_id ? <Badge tone="neutral">task: {runDetail.data.task_id}</Badge> : null}
              <span className="text-xs text-subtle">duration {formatDuration(runDetail.data.duration_ms)}</span>
            </div>

            <KeyValue
              columns={3}
              items={[
                { label: 'Extracted', value: formatNumber(runDetail.data.records_extracted ?? 0) },
                { label: 'Valid', value: formatNumber(runDetail.data.records_valid ?? 0) },
                { label: 'Rejected', value: formatNumber(runDetail.data.records_rejected ?? 0) },
                { label: 'Inserted', value: formatNumber(runDetail.data.records_inserted ?? 0) },
                { label: 'Updated', value: formatNumber(runDetail.data.records_updated ?? 0) },
                { label: 'Duplicates merged', value: formatNumber(runDetail.data.duplicates_merged ?? 0) },
                { label: 'New products', value: formatNumber(runDetail.data.new_products ?? 0) },
                { label: 'Price changes', value: formatNumber(runDetail.data.price_changes ?? 0) },
                { label: 'Removed', value: formatNumber(runDetail.data.removed_products ?? 0) },
              ]}
            />

            {runDetail.data.error_message ? (
              <div className="rounded-lg border border-warning/40 bg-warning-soft p-3 text-xs text-warning">
                {runDetail.data.error_message}
              </div>
            ) : null}

            {runDetail.data.dq?.length ? (
              <div>
                <p className="section-title mb-2">Data quality</p>
                <DataTable
                  rows={runDetail.data.dq}
                  rowKey={(row: any) => row.rule_code}
                  maxHeight={220}
                  columns={[
                    { key: 'code', header: 'Rule', render: (row: any) => <span className="font-mono text-xs">{row.rule_code}</span> },
                    { key: 'name', header: 'Name', render: (row: any) => <span className="block max-w-[16rem] truncate">{row.rule_name}</span> },
                    { key: 'dimension', header: 'Dimension', hideBelow: 'sm', render: (row: any) => <Badge tone="neutral">{row.dimension}</Badge> },
                    { key: 'status', header: 'Status', align: 'center', render: (row: any) => <Badge tone={statusTone(row.status)}>{row.status}</Badge> },
                    { key: 'observed', header: 'Observed', align: 'right', hideBelow: 'md', render: (row: any) => (row.observed_value !== null ? String(row.observed_value) : '—') },
                    { key: 'expected', header: 'Expected', align: 'right', hideBelow: 'lg', render: (row: any) => (row.expected_value !== null ? String(row.expected_value) : '—') },
                  ]}
                />
              </div>
            ) : null}

            {runDetail.data.http?.length ? (
              <div>
                <p className="section-title mb-2">HTTP compliance</p>
                <DataTable
                  rows={runDetail.data.http}
                  rowKey={(row: any, index: number) => `${row.source_code}-${row.host}-${index}`}
                  maxHeight={200}
                  columns={[
                    { key: 'source', header: 'Source', render: (row: any) => <Badge tone="neutral">{row.source_code ?? '—'}</Badge> },
                    { key: 'host', header: 'Host', render: (row: any) => <span className="font-mono text-xs">{row.host ?? '—'}</span> },
                    { key: 'status', header: 'HTTP', align: 'center', render: (row: any) => <Badge tone={statusTone(row.status_code && row.status_code < 400 ? 'success' : 'danger')}>{row.status_code ?? '—'}</Badge> },
                    { key: 'requests', header: 'Requests', align: 'right', render: (row: any) => formatNumber(row.requests ?? 0) },
                    { key: 'avg', header: 'Avg ms', align: 'right', render: (row: any) => Number(row.avg_ms ?? 0).toFixed(1) },
                    { key: 'bytes', header: 'Bytes', align: 'right', hideBelow: 'sm', render: (row: any) => formatCompact(row.bytes ?? 0) },
                    { key: 'blocked', header: 'Blocked', align: 'right', hideBelow: 'md', render: (row: any) => formatNumber(row.blocked ?? 0) },
                    { key: 'cached', header: 'Cached', align: 'right', hideBelow: 'lg', render: (row: any) => formatNumber(row.cached ?? 0) },
                  ]}
                />
              </div>
            ) : null}

            {runDetail.data.reconciliation?.length ? (
              <div>
                <p className="section-title mb-2">Catalog reconciliation</p>
                <DataTable
                  rows={runDetail.data.reconciliation}
                  rowKey={(row: any) => row.match_status}
                  maxHeight={160}
                  columns={[
                    { key: 'status', header: 'Status', render: (row: any) => <Badge tone={statusTone(row.match_status)}>{titleCase(row.match_status)}</Badge> },
                    { key: 'count', header: 'Count', align: 'right', render: (row: any) => formatNumber(row.count ?? 0) },
                    { key: 'mismatch', header: 'Price mismatches', align: 'right', render: (row: any) => formatNumber(row.price_mismatches ?? 0) },
                    { key: 'sim', header: 'Avg similarity', align: 'right', render: (row: any) => (row.avg_similarity !== null ? Number(row.avg_similarity).toFixed(3) : '—') },
                  ]}
                />
              </div>
            ) : null}
          </div>
        ) : (
          <EmptyState title="Run not found" />
        )}
      </Modal>

      {/* ------------------------------------------------------------- trigger modal */}
      <Modal
        open={showTrigger}
        onClose={() => setShowTrigger(false)}
        title="Run the pipeline"
        description="Executes the full ETL synchronously: extract → stage → transform → dedupe → load → detect → reconcile → quality."
        footer={
          <>
            <Button variant="ghost" onClick={() => setShowTrigger(false)}>
              Cancel
            </Button>
            <Button variant="primary" loading={trigger.isPending} onClick={() => trigger.mutate()} icon={<Play className="h-4 w-4" />}>
              Start run
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <div>
            <p className="stat-label mb-1.5">Target database</p>
            <Select value={database} onChange={(event) => setDatabase(event.target.value)}>
              <option value="postgres">PostgreSQL</option>
              <option value="mysql">MySQL</option>
            </Select>
          </div>
          <div>
            <p className="stat-label mb-1.5">Sources (none selected = every enabled source)</p>
            <div className="max-h-48 space-y-1 overflow-auto rounded-lg border border-line p-2">
              {enabledSources.map((source: any) => (
                <Toggle
                  key={source.code}
                  checked={sources.includes(source.code)}
                  onChange={(checked) =>
                    setSources((current) => (checked ? [...current, source.code] : current.filter((item) => item !== source.code)))
                  }
                  label={<span className="font-mono text-xs">{source.code}</span>}
                  description={source.name}
                />
              ))}
            </div>
          </div>
          <div>
            <p className="stat-label mb-1.5">Records per source: {limit}</p>
            <input
              type="range"
              min={5}
              max={400}
              step={5}
              value={limit}
              onChange={(event) => setLimit(Number(event.target.value))}
              className="w-full accent-brand-600"
              aria-label="Records per source"
            />
          </div>
          <div className="space-y-2 rounded-lg border border-line p-3">
            <Toggle checked={skipDq} onChange={setSkipDq} label="Skip data-quality evaluation" description="Not recommended - quality rules are part of the load contract" />
            <Toggle checked={skipCatalog} onChange={setSkipCatalog} label="Skip catalog reconciliation" description="Price-gap analysis will not be refreshed" />
            <Toggle checked={strict} onChange={setStrict} label="Strict validation" description="Reject any record without a parsed price" />
          </div>
        </div>
      </Modal>
    </div>
  )
}

const STAGE_DESCRIPTIONS = [
  'robots.txt-gated HTTP fetch of APIs and permitted pages',
  'raw payloads land in the staging zone unchanged',
  'clean names and categories, normalise price and currency',
  'exact, blocking and fuzzy matching against existing products',
  'upsert dimensions, append immutable price snapshots',
  'compare with the previous snapshot and emit change events',
  'match the internal catalog and compute the price gap',
  'evaluate 12 rules across 6 quality dimensions',
  'refresh the pre-aggregated category/day rollup',
]