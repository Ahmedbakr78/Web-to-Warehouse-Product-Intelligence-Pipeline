/**
 * Settings: global configuration, pipeline schedule, the data-quality rule
 * catalogue and per-source coverage. Editing is admin-only; other roles still get
 * the read-only view so the screen never renders a dead end.
 */

import { useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Boxes, CalendarClock, Database, Lock, RotateCcw, Save, ShieldCheck, SlidersHorizontal } from 'lucide-react'
import { Link } from 'react-router-dom'

import { BarSeries } from '@/components/charts'
import {
  Badge,
  Button,
  Card,
  CardHeader,
  DataTable,
  EmptyState,
  ErrorState,
  IconButton,
  KeyValue,
  LoadingState,
  ProgressBar,
  Tabs,
  TextInput,
  Toggle,
  useToast,
  type Column,
  type Tone,
} from '@/components/ui'
import { endpoints } from '@/lib/api'
import { queryKeys, useApiQuery } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { formatDateTime, formatDuration, formatNumber, formatPrice, formatRelative, titleCase } from '@/lib/format'

type Setting = {
  key: string
  value: string | null
  value_type: string
  category: string
  description: string | null
  is_public: boolean
  updated_at: string | null
}

type Rule = {
  code: string
  name: string
  dimension: string
  severity: string
  description: string
}

type SourceCoverage = {
  source_code: string
  source_name: string
  kind: string
  enabled: boolean
  rate_limit_per_minute: number
  products_seen: number
  observations: number
  avg_price_usd: number | null
  avg_rating: number | null
  last_observation_at: string | null
  success_rate_pct: number | null
  avg_duration_seconds: number | null
}

type Schedule = {
  cron: string
  dag_id: string
  orchestrator: string
  last_run_at: string | null
  next_expected: string | null
  trigger_mix: { trigger: string; count: number }[]
}

function severityTone(severity: string): Tone {
  return severity === 'critical' ? 'danger' : severity === 'high' ? 'warning' : severity === 'medium' ? 'info' : 'neutral'
}

export default function Settings() {
  const queryClient = useQueryClient()
  const toast = useToast()
  const { can } = useAuth()
  const canEdit = can('manage_settings')

  const [tab, setTab] = useState('general')
  const [drafts, setDrafts] = useState<Record<string, string>>({})

  const settings = useApiQuery<Setting[]>(queryKeys.settings(), endpoints.settings)
  const schedule = useApiQuery<Schedule>(['pipeline-schedule'], endpoints.schedule, { staleTime: 60_000 })
  const qualityRules = useApiQuery<Rule[]>(['quality-rules'], endpoints.qualityRules, { staleTime: 300_000 })
  const sources = useApiQuery<SourceCoverage[]>(['source-coverage'], endpoints.sourceCoverage, { staleTime: 60_000 })

  const groups = useMemo(() => {
    const map = new Map<string, Setting[]>()
    for (const row of settings.data ?? []) {
      const bucket = map.get(row.category) ?? []
      bucket.push(row)
      map.set(row.category, bucket)
    }
    return [...map.entries()].sort(([left], [right]) => left.localeCompare(right))
  }, [settings.data])

  const saveSetting = useMutation({
    mutationFn: ({ key, value }: { key: string; value: string }) => endpoints.updateSetting(key, value),
    onSuccess: (_result, variables) => {
      toast.success('Setting saved', variables.key)
      setDrafts((current) => {
        const next = { ...current }
        delete next[variables.key]
        return next
      })
      void queryClient.invalidateQueries({ queryKey: queryKeys.settings() })
    },
    onError: (error: Error) => toast.error('Could not save the setting', error.message),
  })

  const valueOf = (row: Setting) => drafts[row.key] ?? row.value ?? ''
  const isDirty = (row: Setting) => drafts[row.key] !== undefined && drafts[row.key] !== (row.value ?? '')

  const ruleColumns: Column<Rule>[] = [
    { key: 'code', header: 'Code', render: (row) => <span className="font-mono text-xs text-brand-700 dark:text-brand-300">{row.code}</span> },
    { key: 'name', header: 'Rule', render: (row) => <span className="font-medium text-ink">{row.name}</span> },
    { key: 'dimension', header: 'Dimension', hideBelow: 'sm', render: (row) => <Badge tone="neutral">{titleCase(row.dimension)}</Badge> },
    { key: 'severity', header: 'Severity', align: 'center', render: (row) => <Badge tone={severityTone(row.severity)}>{titleCase(row.severity)}</Badge> },
    {
      key: 'description',
      header: 'What it checks',
      hideBelow: 'md',
      render: (row) => <span className="block max-w-[34rem] whitespace-normal text-xs text-muted">{row.description}</span>,
    },
  ]

  const sourceColumns: Column<SourceCoverage>[] = [
    {
      key: 'source',
      header: 'Source',
      render: (row) => (
        <div className="min-w-0">
          <p className="font-medium text-ink">{row.source_name ?? row.source_code}</p>
          <p className="font-mono text-[11px] text-subtle">{row.source_code}</p>
        </div>
      ),
    },
    { key: 'kind', header: 'Kind', hideBelow: 'md', render: (row) => <Badge tone="neutral">{titleCase(row.kind)}</Badge> },
    {
      key: 'state',
      header: 'State',
      align: 'center',
      render: (row) => <Badge tone={row.enabled ? 'success' : 'neutral'} dot>{row.enabled ? 'Enabled' : 'Disabled'}</Badge>,
    },
    { key: 'rate', header: 'Rate limit', align: 'right', hideBelow: 'lg', render: (row) => `${formatNumber(row.rate_limit_per_minute)}/min` },
    { key: 'products', header: 'Products', align: 'right', sortValue: (row) => Number(row.products_seen ?? 0), render: (row) => formatNumber(row.products_seen ?? 0) },
    {
      key: 'observations',
      header: 'Observations',
      align: 'right',
      sortValue: (row) => Number(row.observations ?? 0),
      render: (row) => formatNumber(row.observations ?? 0),
    },
    { key: 'avg_price', header: 'Avg price', align: 'right', hideBelow: 'lg', render: (row) => formatPrice(row.avg_price_usd ?? null) },
    { key: 'avg_rating', header: 'Avg rating', align: 'center', hideBelow: 'xl', render: (row) => (row.avg_rating === null ? <span className="text-subtle">\u2014</span> : Number(row.avg_rating).toFixed(2)) },
    {
      key: 'success',
      header: 'Success rate',
      hideBelow: 'sm',
      width: '10rem',
      render: (row) => {
        const rate = row.success_rate_pct === null ? null : Number(row.success_rate_pct)
        return (
          <div className="flex items-center gap-2">
            <ProgressBar value={rate ?? 0} tone={rate === null ? 'brand' : rate >= 95 ? 'success' : rate >= 80 ? 'warning' : 'danger'} className="w-16" />
            <span className="tabular-nums text-xs text-muted">{rate === null ? '\u2014' : `${rate.toFixed(1)}%`}</span>
          </div>
        )
      },
    },
    { key: 'duration', header: 'Avg latency', align: 'right', hideBelow: 'xl', render: (row) => (row.avg_duration_seconds === null ? <span className="text-subtle">\u2014</span> : formatDuration(Number(row.avg_duration_seconds) * 1000)) },
    {
      key: 'last_seen',
      header: 'Last observation',
      align: 'right',
      hideBelow: 'md',
      sortValue: (row) => (row.last_observation_at ? new Date(row.last_observation_at).getTime() : 0),
      render: (row) => (
        <span className="text-xs text-muted" title={formatDateTime(row.last_observation_at)}>
          {formatRelative(row.last_observation_at)}
        </span>
      ),
    },
  ]

  const triggerMix = (schedule.data?.trigger_mix ?? []).map((item) => ({
    name: titleCase(item.trigger),
    count: Number(item.count ?? 0),
  }))

  return (
    <div className="space-y-4">
      {!canEdit ? (
        <div className="flex items-start gap-2.5 rounded-xl border border-line bg-surface-2 px-3 py-2.5">
          <Lock className="mt-0.5 h-4 w-4 shrink-0 text-subtle" aria-hidden />
          <div>
            <p className="text-sm font-medium text-ink">Read-only view</p>
            <p className="text-xs text-muted">
              Your role can read the configuration but not change it. Editing requires the{' '}
              <code className="rounded bg-surface-3 px-1 font-mono text-[11px]">manage_settings</code> permission.
            </p>
          </div>
        </div>
      ) : null}

      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { id: 'general', label: 'General', count: settings.data?.length, icon: <SlidersHorizontal className="h-4 w-4" /> },
          { id: 'pipeline', label: 'Pipeline', icon: <CalendarClock className="h-4 w-4" /> },
          { id: 'quality', label: 'Data quality', count: qualityRules.data?.length, icon: <ShieldCheck className="h-4 w-4" /> },
          { id: 'sources', label: 'Sources', count: sources.data?.length, icon: <Boxes className="h-4 w-4" /> },
        ]}
      />

      {/* --------------------------------------------------------------- general */}
      {tab === 'general' ? (
        settings.isError ? (
          <ErrorState message={(settings.error as Error)?.message} onRetry={() => settings.refetch()} />
        ) : settings.isLoading && !settings.data ? (
          <LoadingState label="Loading settings\u2026" rows={6} />
        ) : groups.length === 0 ? (
          <Card>
            <EmptyState title="No settings published" message="The settings table is empty for your role." icon={<SlidersHorizontal className="h-7 w-7" />} />
          </Card>
        ) : (
          <div className="space-y-3">
            {groups.map(([category, items]) => (
              <Card key={category} padded={false}>
                <div className="p-4 sm:p-5">
                  <CardHeader
                    title={titleCase(category)}
                    subtitle={`${items.length} key${items.length === 1 ? '' : 's'}`}
                    icon={<SlidersHorizontal className="h-4 w-4" />}
                  />
                </div>
                <ul className="divide-y divide-line">
                  {items.map((row) => (
                    <li key={row.key} className="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:px-5">
                      <div className="min-w-0 flex-1">
                        <p className="font-mono text-xs font-medium text-ink">{row.key}</p>
                        {row.description ? <p className="mt-0.5 text-xs text-subtle">{row.description}</p> : null}
                      </div>

                      <div className="flex flex-wrap items-center gap-2 sm:w-[26rem] sm:justify-end">
                        {row.value_type === 'boolean' ? (
                          <Toggle
                            checked={valueOf(row) === 'true'}
                            disabled={!canEdit}
                            onChange={(next) => setDrafts((current) => ({ ...current, [row.key]: String(next) }))}
                          />
                        ) : (
                          <TextInput
                            type={row.value_type === 'number' ? 'number' : 'text'}
                            step="any"
                            disabled={!canEdit}
                            aria-label={row.key}
                            className={row.value_type === 'json' ? 'font-mono text-xs' : 'sm:w-56'}
                            value={valueOf(row)}
                            placeholder={row.value ?? ''}
                            onChange={(event) => setDrafts((current) => ({ ...current, [row.key]: event.target.value }))}
                          />
                        )}

                        {canEdit ? (
                          <div className="flex items-center gap-1">
                            <IconButton
                              label={`Discard change to ${row.key}`}
                              icon={<RotateCcw className="h-4 w-4" />}
                              disabled={!isDirty(row)}
                              onClick={() =>
                                setDrafts((current) => {
                                  const next = { ...current }
                                  delete next[row.key]
                                  return next
                                })
                              }
                            />
                            <Button
                              size="sm"
                              variant={isDirty(row) ? 'primary' : 'secondary'}
                              icon={<Save className="h-4 w-4" />}
                              disabled={!isDirty(row)}
                              loading={saveSetting.isPending && saveSetting.variables?.key === row.key}
                              onClick={() => saveSetting.mutate({ key: row.key, value: String(valueOf(row)) })}
                            >
                              Save
                            </Button>
                          </div>
                        ) : (
                          <span className="text-[11px] text-subtle">{row.updated_at ? `updated ${formatRelative(row.updated_at)}` : 'never updated'}</span>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              </Card>
            ))}
          </div>
        )
      ) : null}

      {/* --------------------------------------------------------------- pipeline */}
      {tab === 'pipeline' ? (
        schedule.isError ? (
          <ErrorState message={(schedule.error as Error)?.message} onRetry={() => schedule.refetch()} />
        ) : schedule.isLoading && !schedule.data ? (
          <LoadingState label="Loading schedule\u2026" rows={4} />
        ) : (
          <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
            <Card className="xl:col-span-2">
              <CardHeader
                title="Scheduled execution"
                subtitle="The DAG the orchestrator runs on a cron schedule"
                icon={<CalendarClock className="h-4 w-4" />}
                action={
                  <Link to="/pipeline" className="link text-xs">
                    Run history
                  </Link>
                }
              />
              {schedule.data ? (
                <div className="space-y-4">
                  <div className="rounded-lg border border-line bg-surface-2 px-3 py-3">
                    <p className="stat-label">Cron expression</p>
                    <p className="mt-1 font-mono text-sm text-ink">{schedule.data.cron}</p>
                    <p className="mt-1 text-xs text-subtle">
                      Stored as the <code className="font-mono">pipeline.schedule_cron</code> setting \u2014 edit it in the General tab.
                    </p>
                  </div>
                  <KeyValue
                    columns={2}
                    items={[
                      { label: 'DAG id', value: <span className="font-mono text-xs">{schedule.data.dag_id}</span> },
                      { label: 'Orchestrator', value: schedule.data.orchestrator },
                      {
                        label: 'Last run',
                        value: schedule.data.last_run_at ? (
                          <span title={formatDateTime(schedule.data.last_run_at)}>{formatRelative(schedule.data.last_run_at)}</span>
                        ) : (
                          '\u2014'
                        ),
                      },
                      {
                        label: 'Next expected',
                        value: schedule.data.next_expected ? (
                          <span title={formatDateTime(schedule.data.next_expected)}>{formatRelative(schedule.data.next_expected)}</span>
                        ) : (
                          '\u2014'
                        ),
                      },
                    ]}
                  />
                </div>
              ) : (
                <EmptyState title="No schedule configured" />
              )}
            </Card>

            <Card>
              <CardHeader title="Trigger mix" subtitle="How runs were started" icon={<Database className="h-4 w-4" />} />
              {triggerMix.length ? (
                <BarSeries
                  data={triggerMix}
                  xKey="name"
                  bars={[{ key: 'count', label: 'Runs', color: 'var(--chart-1)' }]}
                  height={220}
                />
              ) : (
                <EmptyState title="No runs recorded yet" message="Trigger a run to populate the mix." />
              )}
            </Card>
          </div>
        )
      ) : null}

      {/* --------------------------------------------------------------- data quality */}
      {tab === 'quality' ? (
        qualityRules.isError ? (
          <ErrorState message={(qualityRules.error as Error)?.message} onRetry={() => qualityRules.refetch()} />
        ) : qualityRules.isLoading && !qualityRules.data ? (
          <LoadingState label="Loading rule catalogue\u2026" rows={6} />
        ) : (
          <Card padded={false}>
            <div className="p-4 sm:p-5">
              <CardHeader
                title="Rule catalogue"
                subtitle="Every check the pipeline applies to the warehouse"
                icon={<ShieldCheck className="h-4 w-4" />}
                action={
                  <Link to="/quality" className="link text-xs">
                    Latest results
                  </Link>
                }
              />
            </div>
            <DataTable
              rows={qualityRules.data ?? []}
              columns={ruleColumns}
              rowKey={(row) => row.code}
              loading={qualityRules.isFetching}
              emptyMessage="No data-quality rules registered"
            />
          </Card>
        )
      ) : null}

      {/* --------------------------------------------------------------- sources */}
      {tab === 'sources' ? (
        sources.isError ? (
          <ErrorState message={(sources.error as Error)?.message} onRetry={() => sources.refetch()} />
        ) : sources.isLoading && !sources.data ? (
          <LoadingState label="Loading source coverage\u2026" rows={6} />
        ) : (
          <Card padded={false}>
            <div className="p-4 sm:p-5">
              <CardHeader
                title="Source coverage"
                subtitle="Products, observations, latency and success rate per registered source"
                icon={<Boxes className="h-4 w-4" />}
                action={
                  <Link to="/sources" className="link text-xs">
                    Robots and rate limits
                  </Link>
                }
              />
            </div>
            <DataTable
              rows={sources.data ?? []}
              columns={sourceColumns}
              rowKey={(row) => row.source_code}
              loading={sources.isFetching}
              emptyMessage="No source has reported yet"
            />
          </Card>
        )
      ) : null}

      <p className="flex items-center gap-2 text-[11px] text-subtle">
        <Save className="h-3.5 w-3.5" aria-hidden />
        Values are stored as strings in the settings table and applied on the next pipeline run.
      </p>
    </div>
  )
}