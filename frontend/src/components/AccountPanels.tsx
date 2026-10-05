/**
 * The Account screen's ninth and tenth tabs.
 *
 * These are deliberately built from endpoints that already exist rather than adding
 * new server surface: alert rules and notifications are real resources, and the
 * privacy panel is a readable summary of what `GET /users/me/export` actually
 * contains. A privacy tab that promises controls the server does not enforce would be
 * worse than no tab.
 */

import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import {
  Bell,
  BellOff,
  Database,
  FileDown,
  Gauge,
  HardDrive,
  Mail,
  ShieldCheck,
  Trash2,
  TriangleAlert,
} from 'lucide-react'

import {
  Badge,
  Button,
  Card,
  CardHeader,
  DataTable,
  EmptyState,
  KeyValue,
  Select,
  StatTile,
  TextInput,
  Toggle,
  useToast,
} from '@/components/ui'
import { endpoints } from '@/lib/api'
import { useApiQuery } from '@/hooks/useApi'
import { formatDateTime, formatRelative } from '@/lib/format'

const METRICS = [
  { id: 'price_change_pct', label: 'Price change %' },
  { id: 'rating', label: 'Rating' },
  { id: 'new_product', label: 'New product' },
  { id: 'stock_out', label: 'Out of stock' },
  { id: 'dq_failure', label: 'Data-quality failure' },
]

const OPERATORS = [
  { id: 'lt', label: 'falls below' },
  { id: 'lte', label: 'falls to or below' },
  { id: 'gt', label: 'rises above' },
  { id: 'gte', label: 'rises to or above' },
  { id: 'eq', label: 'equals' },
]

const CHANNELS = [
  { id: 'in_app', label: 'In-app only' },
  { id: 'email', label: 'Email' },
  { id: 'webhook', label: 'Webhook' },
]

/** Human phrasing for a rule, so a threshold of 10 reads as an intention. */
function describeRule(rule: Record<string, unknown>): string {
  const metric = METRICS.find((item) => item.id === rule.metric)?.label ?? String(rule.metric)
  const operator = OPERATORS.find((item) => item.id === rule.operator)?.label ?? String(rule.operator)
  const threshold = rule.metric === 'new_product' || rule.metric === 'dq_failure' ? '' : ` ${Number(rule.threshold)}`
  const scope = rule.category ? ` in ${rule.category}` : ''
  return `${metric} ${operator}${threshold}${scope}`
}

export function AlertsPanel() {
  const toast = useToast()
  const alerts = useApiQuery(['alerts'], endpoints.alerts, { refetchInterval: 60_000 })
  const [name, setName] = useState('')
  const [metric, setMetric] = useState('price_change_pct')
  const [operator, setOperator] = useState('lt')
  const [threshold, setThreshold] = useState('10')
  const [category, setCategory] = useState('')
  const [channel, setChannel] = useState('in_app')

  const create = useMutation({
    mutationFn: () =>
      endpoints.createAlert({
        name: name.trim(),
        metric,
        operator,
        threshold: Number(threshold),
        category: category.trim() || null,
        channel,
      }),
    onSuccess: () => {
      setName('')
      setCategory('')
      void alerts.refetch()
      toast.success('Alert rule created')
    },
    onError: (error: Error) => toast.error('Could not create that rule', error.message),
  })

  const toggle = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
      endpoints.updateAlert(id, { is_active }),
    onSuccess: () => void alerts.refetch(),
    onError: (error: Error) => toast.error('Could not update that rule', error.message),
  })

  const remove = useMutation({
    mutationFn: endpoints.deleteAlert,
    onSuccess: () => {
      void alerts.refetch()
      toast.success('Alert rule deleted')
    },
    onError: (error: Error) => toast.error('Could not delete that rule', error.message),
  })

  const evaluate = useMutation({
    mutationFn: endpoints.evaluateAlerts,
    onSuccess: (result: any) => {
      void alerts.refetch()
      toast.success(
        `Evaluated ${result?.evaluated ?? 0} rule(s)`,
        result?.triggered ? `${result.triggered} fired` : 'Nothing triggered',
      )
    },
    onError: (error: Error) => toast.error('Could not evaluate the rules', error.message),
  })

  const rows = (alerts.data ?? []) as any[]
  const active = rows.filter((row) => row.is_active)

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Rules" value={rows.length} hint="Total, active and paused" icon={<Bell className="h-4 w-4" />} />
        <StatTile label="Active" value={active.length} hint="Evaluated on each run" tone="success" />
        <StatTile
          label="Triggered"
          value={rows.reduce((total, row) => total + (row.trigger_count ?? 0), 0)}
          hint="Lifetime firings"
          tone="warning"
        />
        <StatTile label="Channels" value={new Set(rows.map((row) => row.channel)).size} hint="In-app, email, webhook" />
      </div>

      <Card>
        <CardHeader
          title="Create an alert rule"
          subtitle="Rules are evaluated after each pipeline run and notify you when a metric crosses its threshold"
          icon={<Bell className="h-4 w-4" />}
        />
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          <div>
            <p className="stat-label mb-1.5">Name</p>
            <TextInput
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="e.g. TV price drop"
            />
          </div>
          <div>
            <p className="stat-label mb-1.5">Metric</p>
            <Select value={metric} onChange={(event) => setMetric(event.target.value)}>
              {METRICS.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <p className="stat-label mb-1.5">Condition</p>
            <Select value={operator} onChange={(event) => setOperator(event.target.value)}>
              {OPERATORS.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <p className="stat-label mb-1.5">Threshold</p>
            <TextInput
              value={threshold}
              onChange={(event) => setThreshold(event.target.value)}
              inputMode="decimal"
              disabled={metric === 'new_product' || metric === 'dq_failure'}
            />
          </div>
          <div>
            <p className="stat-label mb-1.5">Category (optional)</p>
            <TextInput
              value={category}
              onChange={(event) => setCategory(event.target.value)}
              placeholder="any category"
            />
          </div>
          <div>
            <p className="stat-label mb-1.5">Channel</p>
            <Select value={channel} onChange={(event) => setChannel(event.target.value)}>
              {CHANNELS.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </Select>
          </div>
        </div>
        <Button
          className="mt-4"
          variant="primary"
          icon={<Bell className="h-4 w-4" />}
          loading={create.isPending}
          disabled={!name.trim()}
          onClick={() => create.mutate()}
        >
          Create rule
        </Button>
      </Card>

      <Card padded={false}>
        <div className="flex flex-wrap items-start justify-between gap-3 p-4 sm:p-5">
          <CardHeader
            title="Your alert rules"
            subtitle="Paused rules are kept but never evaluated"
            icon={<Gauge className="h-4 w-4" />}
          />
          <Button
            size="sm"
            variant="secondary"
            loading={evaluate.isPending}
            onClick={() => evaluate.mutate()}
          >
            Evaluate now
          </Button>
        </div>
        {rows.length ? (
          <DataTable
            rows={rows}
            rowKey={(row: any) => row.alert_id}
            maxHeight={420}
            columns={[
              {
                key: 'name',
                header: 'Rule',
                render: (row: any) => (
                  <div className="min-w-0">
                    <p className="truncate font-medium">{row.name}</p>
                    <p className="truncate text-[11px] text-subtle">{describeRule(row)}</p>
                  </div>
                ),
              },
              {
                key: 'channel',
                header: 'Channel',
                render: (row: any) => (
                  <Badge tone={row.channel === 'email' ? 'info' : row.channel === 'webhook' ? 'warning' : 'neutral'}>
                    {row.channel.replace('_', ' ')}
                  </Badge>
                ),
              },
              {
                key: 'trigger_count',
                header: 'Fired',
                align: 'right',
                render: (row: any) => (
                  <span title={row.last_triggered_at ? formatDateTime(row.last_triggered_at) : 'never fired'}>
                    {row.trigger_count ?? 0}
                  </span>
                ),
              },
              {
                key: 'is_active',
                header: 'State',
                render: (row: any) => (
                  <Toggle
                    checked={Boolean(row.is_active)}
                    onChange={(checked) => toggle.mutate({ id: row.alert_id, is_active: checked })}
                    label={row.is_active ? 'Active' : 'Paused'}
                  />
                ),
              },
              {
                key: 'actions',
                header: '',
                align: 'right',
                render: (row: any) => (
                  <Button
                    size="sm"
                    variant="ghost"
                    icon={<Trash2 className="h-3.5 w-3.5" />}
                    loading={remove.isPending && remove.variables === row.alert_id}
                    onClick={() => remove.mutate(row.alert_id)}
                  >
                    Delete
                  </Button>
                ),
              },
            ]}
          />
        ) : (
          <div className="p-6">
            <EmptyState
              icon={<BellOff className="h-6 w-6" />}
              title="No alert rules yet"
              message="Create one above and it will be evaluated after the next pipeline run."
            />
          </div>
        )}
      </Card>
    </div>
  )
}

export function PrivacyPanel({
  onExport,
  exporting,
  onDelete,
}: {
  onExport: () => void
  exporting: boolean
  onDelete: () => void
}) {
  const notifications = useApiQuery(['notifications', 'account'], () => endpoints.notifications(10), {
    refetchInterval: 60_000,
  })
  const audit = useApiQuery(['audit', 'me', 1], () => endpoints.myActivity({ page: 1, page_size: 5, days: 90 }), { staleTime: 60_000 })

  const unread = (notifications.data?.items ?? []).filter((note: any) => !note.is_read)

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Notifications" value={(notifications.data?.items ?? []).length} hint="Most recent 10" />
        <StatTile label="Unread" value={unread.length} tone={unread.length ? 'warning' : 'success'} />
        <StatTile label="Activity records" value={audit.data?.total ?? 0} hint="90-day window" />
        <StatTile label="Retained activity" value="90 days" hint="Older rows are pruned" />
      </div>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <Card>
          <CardHeader
            title="What is stored about you"
            subtitle="The same set the export contains, itemised"
            icon={<Database className="h-4 w-4" />}
          />
          <KeyValue
            items={[
              { label: 'Profile', value: 'Name, job title, department, avatar colour' },
              { label: 'Preferences', value: 'Theme, accent, density, locale, currency, timezone' },
              { label: 'Credentials', value: 'Argon2id password hash; TOTP secret encrypted at rest' },
              { label: 'Sessions', value: 'Device, address, user agent, sign-in and last-seen times' },
              { label: 'API keys', value: 'Name, prefix, scopes and usage; never the secret' },
              { label: 'Alert rules', value: 'Metric, operator, threshold, channel' },
              { label: 'Activity', value: 'Actions, target, outcome, address, 90-day window' },
            ]}
          />
          <p className="mt-4 flex items-start gap-2 rounded-lg bg-surface-2 p-3 text-[11px] leading-relaxed text-muted">
            <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-brand-500" aria-hidden />
            <span>
              Warehouse data is not owned by your account. Deleting the account removes every personal record
              listed above and leaves the analytics untouched.
            </span>
          </p>
        </Card>

        <Card>
          <CardHeader
            title="Your notifications"
            subtitle="Generated by alert rules and security events"
            icon={<Mail className="h-4 w-4" />}
          />
          {(notifications.data?.items ?? []).length ? (
            <ul className="space-y-2">
              {(notifications.data?.items ?? []).map((note: any) => (
                <li
                  key={note.notification_id}
                  className={`rounded-lg border p-2.5 ${
                    note.is_read ? 'border-line opacity-60' : 'border-brand-500/40 bg-brand-500/5'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-xs font-medium">{note.title}</p>
                    <Badge
                      tone={
                        note.level === 'error' ? 'danger' : note.level === 'warning' ? 'warning' : 'info'
                      }
                    >
                      {note.level}
                    </Badge>
                  </div>
                  {note.body ? <p className="mt-0.5 text-[11px] text-muted">{note.body}</p> : null}
                  <p className="mt-1 text-[11px] text-subtle">{formatRelative(note.created_at)}</p>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState
              icon={<BellOff className="h-6 w-6" />}
              title="Nothing to read"
              message="Notifications appear here when an alert fires or a security event happens."
            />
          )}
          {(notifications.data?.items ?? []).length ? (
            <Button
              className="mt-3"
              size="sm"
              variant="secondary"
              onClick={() => {
                void endpoints.markAllRead()
                void notifications.refetch()
              }}
            >
              Mark all as read
            </Button>
          ) : null}
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Export or delete"
          subtitle="Portability, or removal"
          icon={<HardDrive className="h-4 w-4" />}
        />
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <div className="rounded-xl border border-line bg-surface-2 p-3">
            <p className="flex items-center gap-2 text-sm font-medium">
              <FileDown className="h-4 w-4 text-brand-500" aria-hidden />
              Download everything
            </p>
            <p className="mt-1 text-[11px] leading-relaxed text-muted">
              A single JSON file with your profile, key metadata, saved views, alert rules, notifications and the
              last 90 days of activity. Passwords and key secrets are never included.
            </p>
            <Button
              className="mt-3"
              variant="primary"
              icon={<FileDown className="h-4 w-4" />}
              loading={exporting}
              onClick={onExport}
            >
              Download my data
            </Button>
          </div>
          <div className="rounded-xl border border-danger/40 bg-danger-soft/40 p-3">
            <p className="flex items-center gap-2 text-sm font-medium text-danger">
              <TriangleAlert className="h-4 w-4" aria-hidden />
              Delete my account
            </p>
            <p className="mt-1 text-[11px] leading-relaxed text-muted">
              Requires your password, revokes every API key, session, saved view, alert rule and notification, and
              is irreversible.
            </p>
            <Button
              className="mt-3"
              variant="danger"
              icon={<Trash2 className="h-4 w-4" />}
              onClick={onDelete}
            >
              Delete my account
            </Button>
          </div>
        </div>
      </Card>
    </div>
  )
}
