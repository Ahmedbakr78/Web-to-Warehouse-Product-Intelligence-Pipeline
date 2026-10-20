/**
 * Alerts: per-user threshold rules over the warehouse plus the in-app notification
 * feed. "Matches now" comes from a real evaluation POST, so the column always
 * reflects the current data instead of a stored counter.
 */

import { type ReactNode, useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Bell, BellRing, Check, CheckCheck, Inbox, Pencil, Plus, RefreshCw, Trash2, X, Zap } from 'lucide-react'

import {
  Badge,
  Button,
  Card,
  CardHeader,
  DataTable,
  EmptyState,
  ErrorState,
  IconButton,
  LoadingState,
  Modal,
  Select,
  StatTile,
  Tabs,
  TextInput,
  Toggle,
  useToast,
  type Column,
  type Tone,
} from '@/components/ui'
import { ExportButton } from '@/components/ExportButton'
import { endpoints } from '@/lib/api'
import { queryKeys, useApiQuery } from '@/hooks/useApi'
import { formatDateTime, formatNumber, formatRelative, titleCase } from '@/lib/format'

type AlertRule = {
  alert_id: number
  name: string
  metric: string
  operator: string
  threshold: number
  category: string | null
  source_code: string | null
  is_active: boolean
  channel: string
  last_triggered_at: string | null
  trigger_count: number
  user_id: number | null
}

type Evaluation = {
  evaluated: number
  rules: { alert_id: number; name: string; metric: string; threshold: number; matches_now: number }[]
}

type AppNotification = {
  notification_id: number
  level: string
  title: string
  body: string | null
  is_read: boolean
  created_at: string
}

const EVALUATE_KEY = ['alerts-evaluate']
const FEED_SIZE = 25

const METRICS = [
  { id: 'price_change_pct', label: 'Price change %', hint: 'Counts significant price moves beyond the threshold.' },
  { id: 'rating', label: 'Product rating', hint: 'Counts products rated below the threshold.' },
  { id: 'new_product', label: 'New products', hint: 'Counts arrivals seen in the last seven days.' },
  { id: 'dq_failure', label: 'DQ rule failures', hint: 'Failed data-quality rules in the latest run.' },
  { id: 'stock_out', label: 'Out of stock', hint: 'Counts products currently marked unavailable.' },
]

const OPERATORS = [
  { id: 'lt', label: 'less than  (<)' },
  { id: 'lte', label: 'at most  (≤)' },
  { id: 'gt', label: 'greater than  (>)' },
  { id: 'gte', label: 'at least  (≥)' },
  { id: 'eq', label: 'exactly  (=)' },
]

const CHANNELS = [
  { id: 'in_app', label: 'In-app notification' },
  { id: 'email', label: 'Email' },
  { id: 'webhook', label: 'Webhook' },
]

const EMPTY_FORM = {
  name: '',
  metric: 'price_change_pct',
  operator: 'lt',
  threshold: '5',
  category: '',
  channel: 'in_app',
  isActive: true,
}

type FormState = typeof EMPTY_FORM
type FormErrors = Partial<Record<keyof FormState, string>>

function levelTone(level: string): Tone {
  return level === 'critical' || level === 'error' ? 'danger' : level === 'warning' ? 'warning' : level === 'success' ? 'success' : 'info'
}

function channelTone(channel: string): Tone {
  return channel === 'email' ? 'info' : channel === 'webhook' ? 'brand' : 'neutral'
}

/** The PATCH endpoint replaces every field, so updates must resend the whole rule. */
function rulePayload(rule: AlertRule): Record<string, unknown> {
  return {
    name: rule.name,
    metric: rule.metric,
    operator: rule.operator,
    threshold: Number(rule.threshold),
    category: rule.category ?? null,
    source_code: rule.source_code ?? null,
    channel: rule.channel,
    is_active: Boolean(rule.is_active),
  }
}

export default function Alerts() {
  const queryClient = useQueryClient()
  const toast = useToast()

  const [tab, setTab] = useState('rules')
  const [unreadOnly, setUnreadOnly] = useState(false)
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<AlertRule | null>(null)
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [formErrors, setFormErrors] = useState<FormErrors>({})
  const [pendingDelete, setPendingDelete] = useState<AlertRule | null>(null)

  const rules = useApiQuery<AlertRule[]>(queryKeys.alerts(), endpoints.alerts)
  const evaluation = useApiQuery<Evaluation>(EVALUATE_KEY, endpoints.evaluateAlerts, { staleTime: 60_000 })
  const feed = useApiQuery<{ items?: AppNotification[]; total?: number }>(
    ['notifications', 'alerts-feed', FEED_SIZE, unreadOnly],
    () => endpoints.notifications(FEED_SIZE, unreadOnly),
  )
  const unread = useApiQuery<{ total?: number }>(['notifications', 'alerts-unread'], () => endpoints.notifications(1, true))

  const rows = rules.data ?? []
  const notifications = feed.data?.items ?? []

  const matchesByRule = useMemo(() => {
    const map = new Map<number, number>()
    for (const item of evaluation.data?.rules ?? []) map.set(Number(item.alert_id), Number(item.matches_now ?? 0))
    return map
  }, [evaluation.data])

  const activeCount = rows.filter((row) => row.is_active).length
  const matchingCount = [...matchesByRule.values()].filter((value) => value > 0).length
  const unreadCount = Number(unread.data?.total ?? notifications.filter((item) => !item.is_read).length)

  const refreshAll = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.alerts() })
    void queryClient.invalidateQueries({ queryKey: EVALUATE_KEY })
    void queryClient.invalidateQueries({ queryKey: ['notifications'] })
  }

  const createRule = useMutation({
    mutationFn: (payload: Record<string, unknown>) => endpoints.createAlert(payload),
    onSuccess: () => {
      toast.success('Alert rule created')
      closeForm()
      refreshAll()
    },
    onError: (error: Error) => toast.error('Could not create the rule', error.message),
  })

  const updateRule = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Record<string, unknown> }) => endpoints.updateAlert(id, payload),
    onSuccess: () => {
      toast.success('Alert rule updated')
      closeForm()
      refreshAll()
    },
    onError: (error: Error) => toast.error('Could not update the rule', error.message),
  })

  const toggleRule = useMutation({
    mutationFn: ({ rule, isActive }: { rule: AlertRule; isActive: boolean }) =>
      endpoints.updateAlert(rule.alert_id, { ...rulePayload(rule), is_active: isActive }),
    onSuccess: (_result, variables) => {
      toast.success(variables.isActive ? 'Rule enabled' : 'Rule disabled')
      refreshAll()
    },
    onError: (error: Error) => toast.error('Could not update the rule', error.message),
  })

  const deleteRule = useMutation({
    mutationFn: (id: number) => endpoints.deleteAlert(id),
    onSuccess: (_result, id) => {
      toast.success('Alert rule deleted', `Rule #${id} removed`)
      refreshAll()
    },
    onError: (error: Error) => toast.error('Could not delete the rule', error.message),
  })

  const markAllRead = useMutation({
    mutationFn: () => endpoints.markAllRead(),
    onSuccess: () => {
      toast.success('Notifications cleared')
      void queryClient.invalidateQueries({ queryKey: ['notifications'] })
    },
    onError: (error: Error) => toast.error('Could not mark notifications as read', error.message),
  })

  const markRead = useMutation({
    mutationFn: (id: number) => endpoints.markRead(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['notifications'] }),
  })

  function openCreate() {
    setEditing(null)
    setForm(EMPTY_FORM)
    setFormErrors({})
    setFormOpen(true)
  }

  function openEdit(rule: AlertRule) {
    setEditing(rule)
    setForm({
      name: rule.name,
      metric: rule.metric,
      operator: rule.operator,
      threshold: String(rule.threshold),
      category: rule.category ?? '',
      channel: rule.channel ?? 'in_app',
      isActive: Boolean(rule.is_active),
    })
    setFormErrors({})
    setFormOpen(true)
  }

  function closeForm() {
    setFormOpen(false)
    setEditing(null)
    setFormErrors({})
  }

  function validate(): FormErrors {
    const errors: FormErrors = {}
    const name = form.name.trim()
    if (!name) errors.name = 'Give the rule a recognisable name'
    else if (name.length > 120) errors.name = 'Use 120 characters or fewer'
    if (!METRICS.some((metric) => metric.id === form.metric)) errors.metric = 'Choose a metric to watch'
    if (!OPERATORS.some((operator) => operator.id === form.operator)) errors.operator = 'Choose a comparison'
    if (form.threshold.trim() === '' || !Number.isFinite(Number(form.threshold))) errors.threshold = 'Enter a numeric threshold'
    if (!CHANNELS.some((channel) => channel.id === form.channel)) errors.channel = 'Choose a delivery channel'
    return errors
  }

  function submit() {
    const errors = validate()
    setFormErrors(errors)
    if (Object.keys(errors).length) return
    const payload: Record<string, unknown> = {
      name: form.name.trim(),
      metric: form.metric,
      operator: form.operator,
      threshold: Number(form.threshold),
      category: form.category.trim() || null,
      source_code: null,
      channel: form.channel,
      is_active: form.isActive,
    }
    if (editing) updateRule.mutate({ id: editing.alert_id, payload })
    else createRule.mutate(payload)
  }

  const metricHint = METRICS.find((metric) => metric.id === form.metric)?.hint
  const saving = createRule.isPending || updateRule.isPending

  const columns: Column<AlertRule>[] = [
    {
      key: 'name',
      header: 'Rule',
      sortValue: (row) => row.name,
      render: (row) => (
        <div className="min-w-0">
          <p className="max-w-[16rem] truncate font-medium text-ink">{row.name}</p>
          <p className="text-xs text-subtle">
            {titleCase(row.metric)} · {formatNumber(row.trigger_count)} trigger{row.trigger_count === 1 ? '' : 's'}
          </p>
        </div>
      ),
    },
    {
      key: 'condition',
      header: 'Condition',
      sortValue: (row) => Number(row.threshold),
      render: (row) => (
        <span className="font-mono text-xs text-muted">
          {row.metric} {row.operator} {Number(row.threshold)}
        </span>
      ),
    },
    {
      key: 'scope',
      header: 'Scope',
      hideBelow: 'md',
      render: (row) => (
        <span className="text-xs text-muted">{row.category || row.source_code ? (row.category ?? row.source_code) : 'All products'}</span>
      ),
    },
    {
      key: 'channel',
      header: 'Channel',
      hideBelow: 'lg',
      render: (row) => <Badge tone={channelTone(row.channel)}>{titleCase(row.channel)}</Badge>,
    },
    {
      key: 'matches',
      header: 'Matches now',
      align: 'right',
      sortValue: (row) => matchesByRule.get(row.alert_id) ?? null,
      render: (row) => {
        if (!row.is_active) return <span className="text-subtle">—</span>
        const matches = matchesByRule.get(row.alert_id)
        if (matches === undefined) return <span className="text-xs text-subtle">pending</span>
        return (
          <Badge tone={matches > 0 ? 'warning' : 'neutral'} dot={matches > 0}>
            {formatNumber(matches)}
          </Badge>
        )
      },
    },
    {
      key: 'last_triggered',
      header: 'Last triggered',
      align: 'right',
      hideBelow: 'sm',
      sortValue: (row) => (row.last_triggered_at ? new Date(row.last_triggered_at).getTime() : 0),
      render: (row) => (
        <span className="text-xs text-muted" title={formatDateTime(row.last_triggered_at)}>
          {formatRelative(row.last_triggered_at)}
        </span>
      ),
    },
    {
      key: 'active',
      header: 'Active',
      align: 'center',
      render: (row) => (
        <div className="flex justify-center">
          <Toggle
            checked={Boolean(row.is_active)}
            disabled={toggleRule.isPending}
            onChange={(next) => toggleRule.mutate({ rule: row, isActive: next })}
          />
        </div>
      ),
    },
    {
      key: 'actions',
      header: '',
      align: 'right',
      width: '5.5rem',
      render: (row) => (
        <div className="flex items-center justify-end gap-1">
          <IconButton label={`Edit ${row.name}`} icon={<Pencil className="h-4 w-4" />} onClick={() => openEdit(row)} />
          <IconButton
            label={`Delete ${row.name}`}
            icon={<Trash2 className="h-4 w-4 text-danger" />}
            onClick={() => setPendingDelete(row)}
          />
        </div>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      {/* --------------------------------------------------------------- KPI tiles */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Alert rules"
          value={formatNumber(rows.length)}
          hint={`${formatNumber(rows.filter((row) => row.category).length)} scoped to a category`}
          icon={<Zap className="h-4 w-4" />}
        />
        <StatTile
          label="Active rules"
          value={formatNumber(activeCount)}
          hint={`${formatNumber(rows.length - activeCount)} paused`}
          icon={<BellRing className="h-4 w-4" />}
          tone="success"
        />
        <StatTile
          label="Matching now"
          value={formatNumber(matchingCount)}
          hint={evaluation.isFetching ? 'evaluating against the warehouse…' : `${formatNumber(evaluation.data?.evaluated ?? 0)} rules evaluated`}
          icon={<RefreshCw className="h-4 w-4" />}
          tone={matchingCount > 0 ? 'warning' : 'neutral'}
        />
        <StatTile
          label="Unread notifications"
          value={formatNumber(unreadCount)}
          hint="in-app alerts raised by the pipeline"
          icon={<Bell className="h-4 w-4" />}
          tone={unreadCount > 0 ? 'info' : 'neutral'}
        />
      </div>

      {/* --------------------------------------------------------------- tabs */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <Tabs
          className="min-w-[15rem] flex-1"
          active={tab}
          onChange={setTab}
          tabs={[
            { id: 'rules', label: 'Rules', count: rows.length, icon: <Zap className="h-4 w-4" /> },
            { id: 'notifications', label: 'Notifications', count: unreadCount || undefined, icon: <Bell className="h-4 w-4" /> },
          ]}
        />
        <div className="flex flex-wrap items-center gap-2">
          {tab === 'rules' ? (
            <Button
              size="sm"
              variant="ghost"
              icon={<RefreshCw className={evaluation.isFetching ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />}
              onClick={() => void evaluation.refetch()}
            >
              Evaluate now
            </Button>
          ) : (
            <Button
              size="sm"
              variant="secondary"
              icon={<CheckCheck className="h-4 w-4" />}
              loading={markAllRead.isPending}
              disabled={unreadCount === 0}
              onClick={() => markAllRead.mutate()}
            >
              Mark all read
            </Button>
          )}
          <Button size="sm" variant="primary" icon={<Plus className="h-4 w-4" />} onClick={openCreate}>
            New alert
          </Button>
          <ExportButton dataset="alerts" />
        </div>
      </div>

      {/* --------------------------------------------------------------- rules */}
      {tab === 'rules' ? (
        rules.isError ? (
          <ErrorState message={(rules.error as Error)?.message} onRetry={() => rules.refetch()} />
        ) : rules.isLoading && !rules.data ? (
          <LoadingState label="Loading alert rules…" rows={6} />
        ) : (
          <Card padded={false}>
            <div className="p-4 sm:p-5">
              <CardHeader
                title="Alert rules"
                subtitle="Each rule is evaluated against the warehouse; matching rows raise a notification"
                icon={<BellRing className="h-4 w-4" />}
                action={
                  evaluation.isError ? (
                    <Badge tone="warning">evaluation unavailable</Badge>
                  ) : (
                    <span className="text-xs text-subtle">evaluated {formatRelative(new Date(evaluation.dataUpdatedAt))}</span>
                  )
                }
              />
            </div>
            <DataTable
              rows={rows}
              columns={columns}
              rowKey={(row) => String(row.alert_id)}
              loading={rules.isFetching || evaluation.isFetching}
              emptyMessage="No alert rules yet — create one to watch a metric"
            />
          </Card>
        )
      ) : null}

      {/* --------------------------------------------------------------- notifications */}
      {tab === 'notifications' ? (
        feed.isError ? (
          <ErrorState message={(feed.error as Error)?.message} onRetry={() => feed.refetch()} />
        ) : (
          <Card>
            <CardHeader
              title="Notification feed"
              subtitle="Generated by the pipeline when a rule matches"
              icon={<Inbox className="h-4 w-4" />}
              action={<Toggle checked={unreadOnly} onChange={setUnreadOnly} label="Unread only" />}
            />
            {feed.isLoading && !feed.data ? (
              <LoadingState label="Loading notifications…" rows={4} />
            ) : notifications.length === 0 ? (
              <EmptyState
                title={unreadOnly ? 'Nothing unread' : 'No notifications yet'}
                message={
                  unreadOnly
                    ? 'Every notification has been read. Switch the filter off to see the full history.'
                    : 'Notifications appear here as soon as a rule matches the data.'
                }
                icon={<Inbox className="h-7 w-7" />}
              />
            ) : (
              <ul className="divide-y divide-line">
                {notifications.map((item) => (
                  <li key={item.notification_id} className={item.is_read ? undefined : 'bg-brand-50/50 dark:bg-brand-500/10'}>
                    <div className="flex items-start gap-3 px-1 py-3">
                      <Badge tone={levelTone(item.level)} className="mt-0.5 shrink-0">
                        {titleCase(item.level)}
                      </Badge>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-ink">{item.title}</p>
                        {item.body ? <p className="mt-0.5 text-xs text-muted">{item.body}</p> : null}
                        <p className="mt-1 text-[11px] text-subtle">{formatRelative(item.created_at)}</p>
                      </div>
                      {item.is_read ? null : (
                        <Button
                          size="sm"
                          variant="ghost"
                          icon={<Check className="h-3.5 w-3.5" />}
                          loading={markRead.isPending && markRead.variables === item.notification_id}
                          onClick={() => markRead.mutate(item.notification_id)}
                        >
                          Mark read
                        </Button>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        )
      ) : null}

      <Modal
        open={Boolean(pendingDelete)}
        onClose={() => setPendingDelete(null)}
        title="Delete alert rule"
        size="sm"
        footer={
          <>
            <Button size="sm" variant="ghost" icon={<X className="h-4 w-4" />} onClick={() => setPendingDelete(null)}>
              Cancel
            </Button>
            <Button
              size="sm"
              variant="danger"
              icon={<Trash2 className="h-4 w-4" />}
              loading={deleteRule.isPending}
              onClick={() => {
                if (pendingDelete) deleteRule.mutate(pendingDelete.alert_id)
                setPendingDelete(null)
              }}
            >
              Delete rule
            </Button>
          </>
        }
      >
        <p className="text-sm text-muted">
          <span className="font-medium text-ink">{pendingDelete?.name}</span> will stop raising notifications. This cannot be undone.
        </p>
      </Modal>

      {/* --------------------------------------------------------------- create / edit */}
      <Modal
        open={formOpen}
        onClose={closeForm}
        title={editing ? 'Edit alert rule' : 'New alert rule'}
        description="Rules are evaluated after every pipeline run."
        footer={
          <>
            <Button size="sm" variant="ghost" icon={<X className="h-4 w-4" />} onClick={closeForm}>
              Cancel
            </Button>
            <Button size="sm" variant="primary" icon={editing ? <Pencil className="h-4 w-4" /> : <Plus className="h-4 w-4" />} loading={saving} onClick={submit}>
              {editing ? 'Save changes' : 'Create rule'}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Field label="Name" error={formErrors.name}>
            <TextInput
              value={form.name}
              maxLength={120}
              placeholder="e.g. Big price moves on laptops"
              onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
            />
          </Field>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Metric" error={formErrors.metric}>
              <Select
                value={form.metric}
                aria-label="Metric"
                onChange={(event) => setForm((current) => ({ ...current, metric: event.target.value }))}
              >
                {METRICS.map((metric) => (
                  <option key={metric.id} value={metric.id}>
                    {metric.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Comparison" error={formErrors.operator}>
              <Select
                value={form.operator}
                aria-label="Comparison"
                onChange={(event) => setForm((current) => ({ ...current, operator: event.target.value }))}
              >
                {OPERATORS.map((operator) => (
                  <option key={operator.id} value={operator.id}>
                    {operator.label}
                  </option>
                ))}
              </Select>
            </Field>
          </div>

          <Field label="Threshold" error={formErrors.threshold} hint={metricHint}>
            <TextInput
              type="number"
              inputMode="decimal"
              step="any"
              value={form.threshold}
              onChange={(event) => setForm((current) => ({ ...current, threshold: event.target.value }))}
            />
          </Field>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Category" hint="Optional — limits the rule to one category">
              <TextInput
                value={form.category}
                placeholder="e.g. Laptops"
                onChange={(event) => setForm((current) => ({ ...current, category: event.target.value }))}
              />
            </Field>
            <Field label="Channel" error={formErrors.channel}>
              <Select
                value={form.channel}
                aria-label="Channel"
                onChange={(event) => setForm((current) => ({ ...current, channel: event.target.value }))}
              >
                {CHANNELS.map((channel) => (
                  <option key={channel.id} value={channel.id}>
                    {channel.label}
                  </option>
                ))}
              </Select>
            </Field>
          </div>

          <div className="border-t border-line pt-3">
            <Toggle
              checked={form.isActive}
              onChange={(next) => setForm((current) => ({ ...current, isActive: next }))}
              label="Active"
              description="Paused rules are skipped during evaluation."
            />
          </div>
        </div>
      </Modal>
    </div>
  )
}

/* ------------------------------------------------------------------------------------
   Labelled form field with inline validation message
   ------------------------------------------------------------------------------------ */
function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string
  hint?: string
  error?: string
  children: ReactNode
}) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-ink">{label}</label>
      {children}
      {error ? (
        <p className="mt-1 text-xs text-danger">{error}</p>
      ) : hint ? (
        <p className="mt-1 text-xs text-subtle">{hint}</p>
      ) : null}
    </div>
  )
}