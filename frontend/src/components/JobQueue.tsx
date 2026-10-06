/**
 * Background job queue with live progress.
 *
 * The list is a normal paginated query, but anything queued or running is tracked over
 * SSE so a long export or backfill shows progress without the user refreshing. A job
 * that disappears from the active set keeps its last known state in a ref, so the
 * panel does not flicker back to "queued" between events.
 */

import { useMemo, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Ban,
  CircleCheck,
  CircleDashed,
  CircleX,
  ListRestart,
  Timer,
  Zap,
} from 'lucide-react'

import { Badge, Button, Card, CardHeader, DataTable, KeyValue, ProgressBar, useToast } from '@/components/ui'
import { endpoints } from '@/lib/api'
import { useApiQuery } from '@/hooks/useApi'
import { useEventStream, useJob } from '@/lib/stream'
import { formatDateTime, formatRelative } from '@/lib/format'
import { cn } from '@/lib/cn'

const ACTIVE = ['queued', 'running']
const TERMINAL = ['succeeded', 'failed', 'cancelled']

const TONE = {
  queued: 'neutral',
  running: 'info',
  succeeded: 'success',
  failed: 'danger',
  cancelled: 'warning',
} as Record<string, any>

const ICON = {
  queued: CircleDashed,
  running: Timer,
  succeeded: CircleCheck,
  failed: CircleX,
  cancelled: Ban,
} as Record<string, any>

/** Progress bar plus caption, since the shared ProgressBar has no label slot. */
function JobProgress({ value, caption }: { value: number; caption?: string }) {
  const tone = value >= 100 ? 'success' : 'brand'
  return (
    <div className="min-w-[140px]">
      <ProgressBar value={value} tone={tone} />
      <p className="mt-1 truncate text-[11px] text-subtle">{caption ?? `${Math.round(value)}%`}</p>
    </div>
  )
}

/** Friendly names for the job types `GET /jobs/types` reports. */
const LABELS: Record<string, string> = {
  pipeline_run: 'Pipeline run',
  backfill: 'Backfill',
  export: 'Export',
  forecast: 'Forecast rebuild',
  rebuild_aggregates: 'Aggregate rebuild',
  report_pdf: 'Report PDF',
}

export default function JobQueue() {
  const toast = useToast()
  const queryClient = useQueryClient()
  const [expanded, setExpanded] = useState<string | null>(null)

  const jobs = useApiQuery(['jobs', 'queue'], () => endpoints.jobs({ limit: 25 }), { refetchInterval: 15_000 })
  const worker = useApiQuery(['jobs', 'worker'], endpoints.jobWorker, { refetchInterval: 30_000 })
  const types = useApiQuery(['jobs', 'types'], endpoints.jobTypes, { staleTime: 300_000 })

  // Progress pushed over the stream wins over the polled row, but only while the job
  // is still active - afterwards the database row is the source of truth.
  const live = useRef(new Map<string, Record<string, any>>())
  const { state, events: streamEvents } = useEventStream(['job'], {
    onEvent: (event) => {
      const reference = String(event.job_key ?? event.job_reference ?? '')
      if (!reference) return
      if (TERMINAL.includes(String(event.status ?? ''))) live.current.delete(reference)
      else live.current.set(reference, event)
    },
  })

  const cancel = useMutation({
    mutationFn: endpoints.cancelJob,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['jobs'] })
      toast.success('Cancellation requested', 'A running job stops at its next checkpoint')
    },
    onError: (error) => toast.error('Could not cancel that job', (error as Error).message),
  })

  const retry = useMutation({
    mutationFn: endpoints.retryJob,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['jobs'] })
      toast.success('Job re-queued')
    },
    onError: (error) => toast.error('Could not retry that job', (error as Error).message),
  })

  const detailJob = useJob(expanded)
  const detail = expanded && detailJob.job && !detailJob.loading ? (detailJob.job as any) : null
  const events = (detail?.events ?? []) as any[]

  const rows = useMemo(() => {
    const items = (jobs.data?.items ?? []) as any[]
    return items.map((row) => {
      // The stream keys events by job_key (falling back to a legacy reference);
      // match either so pushed progress always lands on its row.
      const push = live.current.get(row.job_key) ?? live.current.get(row.reference)
      if (!push || TERMINAL.includes(String(row.status))) return row
      return {
        ...row,
        status: push.status ?? row.status,
        progress_pct: push.progress_pct ?? row.progress_pct,
        stage: push.stage ?? row.stage,
        message: push.message ?? row.message,
        streamed: true,
      }
    })
    // `streamEvents` is the re-render trigger: `live` is a ref mutated in place,
    // so without it the merged progress would sit stale until the next 15 s poll.
  }, [jobs.data, streamEvents])

  const active = rows.filter((row) => ACTIVE.includes(String(row.status)))
  const cancellable = new Set<string>(types.data?.cancellable ?? [])
  const streamState = state === 'open' ? 'live' : state

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[
          { label: 'Active', value: active.length, tone: active.length ? 'text-info' : 'text-ink' },
          { label: 'Running now', value: rows.filter((row) => row.status === 'running').length, tone: 'text-ink' },
          {
            label: 'Succeeded (last 25)',
            value: rows.filter((row) => row.status === 'succeeded').length,
            tone: 'text-success',
          },
          {
            label: 'Failed (last 25)',
            value: rows.filter((row) => row.status === 'failed').length,
            tone: 'text-danger',
          },
        ].map((item) => (
          <Card key={item.label} className="px-4 py-3">
            <p className="stat-label">{item.label}</p>
            <p className={cn('mt-0.5 text-2xl font-semibold tabular-nums', item.tone)}>{item.value}</p>
          </Card>
        ))}
      </div>

      <Card padded={false}>
        <div className="flex flex-wrap items-start justify-between gap-3 p-4 sm:p-5">
          <CardHeader
            title="Background jobs"
            subtitle="Exports, backfills, forecasts and report rendering, with live progress"
            icon={<Zap className="h-4 w-4" />}
          />
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={streamState === 'live' ? 'success' : streamState === 'connecting' ? 'warning' : 'neutral'}>
              {streamState === 'live' ? 'Live' : streamState === 'connecting' ? 'Connecting' : 'Polling'}
            </Badge>
            {worker.data?.running ? <Badge tone="info">worker busy</Badge> : <Badge tone="neutral">worker idle</Badge>}
            <Button size="sm" variant="ghost" onClick={() => void jobs.refetch()}>
              Refresh
            </Button>
          </div>
        </div>

        {rows.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-14 text-center">
            <Zap className="h-8 w-8 text-subtle" aria-hidden />
            <p className="text-sm text-muted">No jobs yet</p>
            <p className="max-w-sm text-xs text-subtle">
              Triggering a pipeline run, export or backfill queues a job here.
            </p>
          </div>
        ) : (
          <DataTable
            rows={rows}
            rowKey={(row: any) => row.job_key}
            maxHeight={520}
            onRowClick={(row: any) => setExpanded((current) => (current === row.job_key ? null : row.job_key))}
            columns={[
              {
                key: 'job_type',
                header: 'Job',
                render: (row: any) => {
                  const Icon = ICON[String(row.status)] ?? CircleDashed
                  return (
                    <div className="flex items-center gap-2">
                      <Icon className="h-4 w-4 shrink-0 text-subtle" aria-hidden />
                      <div className="min-w-0">
                        <p className="truncate font-medium">{LABELS[row.job_type] ?? row.job_type}</p>
                        <p className="truncate font-mono text-[11px] text-subtle">{row.job_key}</p>
                      </div>
                    </div>
                  )
                },
              },
              {
                key: 'progress',
                header: 'Progress',
                render: (row: any) => (
                  <JobProgress
                    value={Number(row.progress_pct ?? 0)}
                    caption={row.stage ?? (row.message ? String(row.message) : undefined)}
                  />
                ),
              },
              {
                key: 'status',
                header: 'Status',
                render: (row: any) => (
                  <div className="flex flex-wrap items-center gap-1">
                    <Badge tone={TONE[String(row.status)] ?? 'neutral'}>{String(row.status)}</Badge>
                    {row.streamed ? <Badge tone="info">live</Badge> : null}
                  </div>
                ),
              },
              {
                key: 'created_at',
                header: 'Queued',
                render: (row: any) => <span title={formatDateTime(row.queued_at)}>{formatRelative(row.queued_at)}</span>,
              },
              {
                key: 'actions',
                header: '',
                align: 'right',
                render: (row: any) => (
                  <div className="flex items-center justify-end gap-1">
                    {ACTIVE.includes(String(row.status)) && cancellable.has(String(row.job_type)) ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        icon={<Ban className="h-3.5 w-3.5" />}
                        disabled={cancel.isPending}
                        onClick={() => cancel.mutate(row.job_key)}
                      >
                        Cancel
                      </Button>
                    ) : null}
                    {['failed', 'cancelled'].includes(String(row.status)) ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        icon={<ListRestart className="h-3.5 w-3.5" />}
                        disabled={retry.isPending}
                        onClick={() => retry.mutate(row.job_key)}
                      >
                        Retry
                      </Button>
                    ) : null}
                  </div>
                ),
              },
            ]}
          />
        )}
      </Card>

      {detail ? (
        <Card>
          <CardHeader
            title={`${LABELS[detail.job_type] ?? detail.job_type} · ${detail.job_key}`}
            subtitle={detail.message ?? 'Progress log for this job'}
            icon={<Timer className="h-4 w-4" />}
          />
          <KeyValue
            items={[
              { label: 'Status', value: String(detail.status ?? 'unknown') },
              { label: 'Attempt', value: `${detail.attempt ?? 1} of ${detail.max_attempts ?? 3}` },
              { label: 'Queued', value: formatDateTime(detail.queued_at) },
              {
                label: 'Started',
                value: detail.started_at ? formatDateTime(detail.started_at) : 'not yet',
              },
              {
                label: 'Finished',
                value: detail.finished_at ? formatDateTime(detail.finished_at) : 'still running',
              },
              { label: 'Requested by', value: detail.requested_by_email ?? 'scheduler or API' },
              {
                label: 'Result',
                value: detail.result?.filename ?? (detail.result ? Object.keys(detail.result)[0] : '—'),
              },
            ]}
          />
          {detail.error ? (
            <p className="mt-3 rounded-lg bg-danger-soft p-3 text-[11px] leading-relaxed text-danger">{String(detail.error)}</p>
          ) : null}
          <ol className="mt-4 space-y-2 border-l border-line pl-4">
            {events.map((event: any) => (
              <li key={event.event_id} className="relative">
                <span className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full bg-brand-500" aria-hidden />
                <p className="text-xs font-medium text-ink">{event.stage ?? event.status ?? 'update'}</p>
                {event.message ? <p className="text-[11px] text-muted">{event.message}</p> : null}
                <p className="text-[11px] text-subtle">
                  {event.progress_pct ?? 0}% · {formatRelative(event.created_at)}
                </p>
              </li>
            ))}
            {!events.length ? <li className="text-[11px] text-subtle">No progress events recorded yet.</li> : null}
          </ol>
        </Card>
      ) : null}
    </div>
  )
}