import { useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle2, Info, RefreshCw, ShieldCheck, ShieldQuestion, XCircle } from 'lucide-react'

import { LineTrend, DonutChart } from '@/components/charts'
import {
  Badge,
  Button,
  Card,
  CardHeader,
  DataTable,
  EmptyState,
  ErrorState,
  LoadingState,
  ProgressBar,
  SearchInput,
  Segmented,
  Select,
  StatTile,
  Tabs,
} from '@/components/ui'
import { cn } from '@/lib/cn'
import { ExportButton } from '@/components/ExportButton'
import { endpoints } from '@/lib/api'
import { useApiQuery } from '@/hooks/useApi'
import { useDebounce } from '@/hooks/useDebounce'
import { formatDateTime, formatNumber, formatRelative, statusTone, titleCase } from '@/lib/format'

const RANGES = [
  { id: '30', label: '30d' },
  { id: '90', label: '90d' },
  { id: '365', label: '1y' },
]

const DIMENSIONS = [
  { id: '', label: 'All dimensions' },
  { id: 'completeness', label: 'Completeness' },
  { id: 'validity', label: 'Validity' },
  { id: 'uniqueness', label: 'Uniqueness' },
  { id: 'consistency', label: 'Consistency' },
  { id: 'accuracy', label: 'Accuracy' },
  { id: 'timeliness', label: 'Timeliness' },
]

export default function Quality() {
  const [tab, setTab] = useState('overview')
  const [range, setRange] = useState('90')
  const [dimension, setDimension] = useState('')
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounce(search, 300)

  const latest = useApiQuery(['quality-latest'], endpoints.qualityLatest)
  const rules = useApiQuery(['quality-rules'], endpoints.qualityRules, { staleTime: 600_000 })
  const trend = useApiQuery(['quality-trend', range], () => endpoints.qualityTrend(Number(range)))
  const summary = useApiQuery(['quality-summary'], endpoints.qualitySummary)

  const resultsParams = useMemo(
    () => ({ page: 1, page_size: 100, dimension: dimension || undefined, status: status || undefined }),
    [dimension, status],
  )
  const results = useApiQuery(['quality-results', resultsParams], () => endpoints.qualityResults(resultsParams))

  const report = latest.data ?? {}
  const score = Number(report.score ?? 0)
  const rulesList: any[] = report.rules ?? []

  const filteredResults = debouncedSearch
    ? (results.data?.items ?? []).filter((row: any) =>
        `${row.rule_code} ${row.rule_name} ${row.message ?? ''}`.toLowerCase().includes(debouncedSearch.toLowerCase()),
      )
    : (results.data?.items ?? [])

  const statusCounts = (summary.data?.by_status ?? []).reduce((acc: Record<string, number>, item: any) => {
    acc[item.status] = (acc[item.status] ?? 0) + item.count
    return acc
  }, {})

  if (latest.isError) {
    return <ErrorState title="Could not load the quality report" message={(latest.error as Error)?.message} onRetry={() => latest.refetch()} />
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Tabs
          active={tab}
          onChange={setTab}
          tabs={[
            { id: 'overview', label: 'Overview', icon: <ShieldCheck className="h-4 w-4" /> },
            { id: 'rules', label: 'Rule catalogue', count: rules.data?.length ?? 0 },
            { id: 'history', label: 'History', count: results.data?.total ?? 0 },
          ]}
        />
        <div className="flex items-center gap-2">
          <Segmented options={RANGES} value={range} onChange={setRange} size="sm" />
          <Button size="sm" variant="ghost" icon={<RefreshCw className={cn('h-4 w-4', latest.isFetching && 'animate-spin')} />} onClick={() => void latest.refetch()}>
            Refresh
          </Button>
        </div>
      </div>

      {tab === 'overview' ? (
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <StatTile
              label="Quality score"
              value={score ? score.toFixed(2) : '—'}
              hint={`Weighted across ${report.total ?? 0} rules`}
              icon={<ShieldCheck className="h-4 w-4" />}
              tone={score >= 90 ? 'success' : score >= 75 ? 'warning' : 'danger'}
            />
            <StatTile label="Rules passed" value={formatNumber(report.pass ?? 0)} hint="Within threshold" icon={<CheckCircle2 className="h-4 w-4" />} tone="success" />
            <StatTile label="Rules warned" value={formatNumber(report.warn ?? 0)} hint="Between 95% and threshold" icon={<ShieldQuestion className="h-4 w-4" />} tone="warning" />
            <StatTile
              label="Rules failed"
              value={formatNumber(report.fail ?? 0)}
              hint={(report.blocking ?? []).length ? `Blocking: ${report.blocking.join(', ')}` : 'No blocking failures'}
              icon={<XCircle className="h-4 w-4" />}
              tone={report.fail ? 'danger' : 'neutral'}
            />
          </div>

          <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
            <Card>
              <CardHeader
                title="Score"
                subtitle={`Run ${report.run_id?.slice(0, 12) ?? '—'}`}
                icon={<ShieldCheck className="h-4 w-4" />}
                action={<ExportButton dataset="quality" />}
              />
              {latest.isLoading ? (
                <LoadingState label="Loading score…" rows={2} />
              ) : (
                <>
                  <div className="mb-3 flex items-end gap-2">
                    <span className="text-4xl font-semibold tabular-nums">{score.toFixed(1)}</span>
                    <span className="mb-1 text-sm text-subtle">/ 100</span>
                  </div>
                  <ProgressBar value={score} tone={score >= 90 ? 'success' : score >= 75 ? 'warning' : 'danger'} />
                  <p className="mt-3 text-xs leading-relaxed text-muted">
                    The score weights every rule by severity (critical 1.0, error 1.5, warn 2.0) and by outcome (pass 1.0,
                    warn 0.75, fail 0.0). A <strong>critical</strong> failure blocks the run; an error is recorded and
                    surfaced without failing the pipeline.
                  </p>
                </>
              )}
            </Card>

            <Card>
              <CardHeader title="By dimension" subtitle="Six dimensions of data quality" icon={<Info className="h-4 w-4" />} />
              {summary.data?.by_dimension?.length ? (
                <div className="space-y-2.5">
                  {Object.entries(
                    summary.data.by_dimension.reduce((acc: Record<string, any>, row: any) => {
                      acc[row.dimension] = row
                      return acc
                    }, {}),
                  ).map(([dimensionName, row]: any) => {
                    const total = Number(row.pass ?? 0) + Number(row.warn ?? 0) + Number(row.fail ?? 0)
                    const passRate = total ? (Number(row.pass) / total) * 100 : 0
                    return (
                      <div key={dimensionName}>
                        <div className="mb-1 flex items-center justify-between text-xs">
                          <span className="font-medium capitalize text-ink">{dimensionName}</span>
                          <span className="tabular-nums text-subtle">
                            {row.pass ?? 0}/{total}
                          </span>
                        </div>
                        <ProgressBar value={passRate} tone={passRate >= 95 ? 'success' : passRate >= 70 ? 'warning' : 'danger'} />
                      </div>
                    )
                  })}
                </div>
              ) : (
                <EmptyState kind="shield" title="No results recorded yet" message="Run the pipeline to evaluate the rules." />
              )}
            </Card>

            <Card>
              <CardHeader title="Outcome mix" subtitle="All recorded rule evaluations" icon={<ShieldCheck className="h-4 w-4" />} />
              {summary.data?.by_status?.length ? (
                <DonutChart
                  data={summary.data.by_status.map((row: any) => ({ name: titleCase(row.status), value: row.count }))}
                  height={220}
                  centerLabel="evaluations"
                />
              ) : (
                <EmptyState kind="shield" title="No data" />
              )}
            </Card>
          </div>

          <Card padded={false}>
            <div className="p-4 sm:p-5">
              <CardHeader
                title="Latest evaluation"
                subtitle={report.evaluated_at ? `${formatDateTime(report.evaluated_at)} · ${formatRelative(report.evaluated_at)}` : undefined}
                icon={<ShieldCheck className="h-4 w-4" />}
              />
            </div>
            <DataTable
              rows={rulesList}
              rowKey={(row: any) => row.code}
              loading={latest.isFetching}
              emptyMessage="No evaluation results for this run"
              columns={[
                { key: 'code', header: 'Rule', render: (row: any) => <span className="font-mono text-xs">{row.code}</span> },
                { key: 'name', header: 'Name', render: (row: any) => <span className="block max-w-[16rem] truncate">{row.name}</span> },
                { key: 'dimension', header: 'Dimension', hideBelow: 'sm', render: (row: any) => <Badge tone="neutral">{row.dimension}</Badge> },
                { key: 'severity', header: 'Severity', align: 'center', hideBelow: 'md', render: (row: any) => <Badge tone={row.severity === 'critical' ? 'danger' : row.severity === 'error' ? 'warning' : 'neutral'}>{row.severity}</Badge> },
                { key: 'status', header: 'Status', align: 'center', render: (row: any) => <Badge tone={statusTone(row.status)} dot>{row.status}</Badge> },
                { key: 'observed', header: 'Observed', align: 'right', render: (row: any) => (row.observed_value !== null ? Number(row.observed_value).toFixed(3) : '—') },
                { key: 'expected', header: 'Expected', align: 'right', hideBelow: 'sm', render: (row: any) => (row.expected_value !== null ? String(row.expected_value) : '—') },
                { key: 'checked', header: 'Checked', align: 'right', hideBelow: 'lg', render: (row: any) => formatNumber(row.records_checked ?? 0) },
                { key: 'failed', header: 'Failed', align: 'right', hideBelow: 'lg', render: (row: any) => formatNumber(row.records_failed ?? 0) },
                { key: 'message', header: 'Message', hideBelow: 'xl', render: (row: any) => <span className="block max-w-[22rem] truncate text-xs text-muted">{row.message ?? '—'}</span> },
              ]}
            />
          </Card>

          {trend.data?.length ? (
            <Card>
              <CardHeader title="Score trend" subtitle={`Quality score per run over ${range} days`} icon={<ShieldCheck className="h-4 w-4" />} />
              <LineTrend
                data={trend.data.map((row: any) => ({ ...row, date: formatDateTime(row.started_at).slice(0, 16) }))}
                xKey="date"
                series={[{ key: 'dq_score', label: 'Quality score', color: 'var(--chart-3)' }]}
                height={240}
              />
            </Card>
          ) : null}

          {summary.data?.problem_rules?.length ? (
            <Card padded={false}>
              <div className="p-4 sm:p-5">
                <CardHeader title="Findings needing attention" subtitle="Warnings and failures from the most recent evaluations" icon={<AlertTriangle className="h-4 w-4" />} />
              </div>
              <DataTable
                rows={summary.data.problem_rules}
                rowKey={(row: any, index: number) => `${row.rule_code}-${index}`}
                columns={[
                  { key: 'code', header: 'Rule', render: (row: any) => <span className="font-mono text-xs">{row.rule_code}</span> },
                  { key: 'name', header: 'Name', render: (row: any) => row.rule_name },
                  { key: 'severity', header: 'Severity', align: 'center', render: (row: any) => <Badge tone={row.severity === 'critical' ? 'danger' : 'warning'}>{row.severity}</Badge> },
                  { key: 'status', header: 'Status', align: 'center', render: (row: any) => <Badge tone={statusTone(row.status)}>{row.status}</Badge> },
                  { key: 'message', header: 'Message', render: (row: any) => <span className="block max-w-[28rem] truncate text-xs text-muted">{row.message ?? '—'}</span> },
                ]}
              />
            </Card>
          ) : null}
        </>
      ) : null}

      {tab === 'rules' ? (
        <Card padded={false}>
          <div className="p-4 sm:p-5">
            <CardHeader
              title="Rule catalogue"
              subtitle="Every rule is declarative, unit tested and re-usable from the CLI, API and Airflow"
              icon={<ShieldCheck className="h-4 w-4" />}
            />
          </div>
          <DataTable
            rows={rules.data ?? []}
            rowKey={(row: any) => row.code}
            loading={rules.isLoading}
            emptyMessage="No rules registered"
            columns={[
              { key: 'code', header: 'Code', render: (row: any) => <span className="font-mono text-xs">{row.code}</span> },
              { key: 'name', header: 'Name', render: (row: any) => <span className="font-medium">{row.name}</span> },
              { key: 'dimension', header: 'Dimension', render: (row: any) => <Badge tone="neutral">{row.dimension}</Badge> },
              {
                key: 'severity',
                header: 'Severity',
                align: 'center',
                render: (row: any) => (
                  <Badge tone={row.severity === 'critical' ? 'danger' : row.severity === 'error' ? 'warning' : row.severity === 'info' ? 'info' : 'neutral'}>
                    {row.severity}
                  </Badge>
                ),
              },
              { key: 'description', header: 'Description', render: (row: any) => <span className="block max-w-[32rem] text-xs text-muted">{row.description}</span> },
            ]}
          />
        </Card>
      ) : null}

      {tab === 'history' ? (
        <Card padded={false}>
          <div className="space-y-2 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <SearchInput value={search} onChange={setSearch} placeholder="Filter rules or messages…" className="w-64" />
              <Select value={dimension} onChange={(event) => setDimension(event.target.value)} aria-label="Dimension" className="w-48">
                {DIMENSIONS.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.label}
                  </option>
                ))}
              </Select>
              <Select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Status" className="w-36">
                <option value="">All statuses</option>
                <option value="pass">Pass</option>
                <option value="warn">Warn</option>
                <option value="fail">Fail</option>
              </Select>
              <div className="ml-auto flex items-center gap-2 text-xs text-subtle">
                <Badge tone="success">{statusCounts.pass ?? 0} pass</Badge>
                <Badge tone="warning">{statusCounts.warn ?? 0} warn</Badge>
                <Badge tone="danger">{statusCounts.fail ?? 0} fail</Badge>
              </div>
            </div>
          </div>
          <DataTable
            rows={filteredResults}
            rowKey={(row: any) => String(row.result_id)}
            loading={results.isFetching}
            emptyMessage="No evaluation history for these filters"
            columns={[
              { key: 'evaluated', header: 'Evaluated', render: (row: any) => <span title={formatDateTime(row.evaluated_at)}>{formatRelative(row.evaluated_at)}</span> },
              { key: 'run', header: 'Run', hideBelow: 'xl', render: (row: any) => <span className="font-mono text-[10px]">{row.run_id?.slice(0, 10)}</span> },
              { key: 'code', header: 'Rule', render: (row: any) => <span className="font-mono text-xs">{row.rule_code}</span> },
              { key: 'name', header: 'Name', hideBelow: 'sm', render: (row: any) => <span className="block max-w-[18rem] truncate">{row.rule_name}</span> },
              { key: 'dimension', header: 'Dimension', hideBelow: 'lg', render: (row: any) => <Badge tone="neutral">{row.dimension}</Badge> },
              { key: 'status', header: 'Status', align: 'center', render: (row: any) => <Badge tone={statusTone(row.status)} dot>{row.status}</Badge> },
              { key: 'passrate', header: 'Pass rate', align: 'right', hideBelow: 'md', render: (row: any) => (row.pass_rate_pct !== null && row.pass_rate_pct !== undefined ? `${Number(row.pass_rate_pct).toFixed(2)}%` : '—') },
              { key: 'failed', header: 'Failed', align: 'right', hideBelow: 'lg', render: (row: any) => formatNumber(row.records_failed ?? 0) },
              { key: 'message', header: 'Message', hideBelow: 'md', render: (row: any) => <span className="block max-w-[26rem] truncate text-xs text-muted">{row.message ?? '—'}</span> },
            ]}
          />
        </Card>
      ) : null}
    </div>
  )
}