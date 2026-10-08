/**
 * Webhooks: outbound event subscriptions with HMAC signing, retries and a delivery log.
 *
 * The signing secret is returned exactly once by the API (like an API key), so this page
 * reveals it in a one-time panel the moment a subscription is created or rotated, and
 * never stores it in component state beyond that.
 */

import { useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  Copy,
  KeyRound,
  Plus,
  RefreshCw,
  RotateCw,
  Check,
  Send,
  Trash2,
  Webhook as WebhookIcon,
  X,
  XCircle,
} from 'lucide-react'

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
  TextInput,
  Toggle,
  useToast,
  type Column,
} from '@/components/ui'
import { endpoints } from '@/lib/api'
import { useApiQuery } from '@/hooks/useApi'
import { formatDateTime, formatNumber } from '@/lib/format'

type Webhook = {
  webhook_id: number
  name: string
  target_url: string
  description: string | null
  events: string[]
  is_active: boolean
  success_count: number
  failure_count: number
  consecutive_failures: number
  last_status_code: number | null
  last_error: string | null
  last_triggered_at: string | null
  disabled_reason: string | null
  created_at: string | null
  secret?: string | null
}

type Delivery = {
  delivery_id: number
  event: string
  status: string
  attempts: number
  status_code: number | null
  error: string | null
  response_excerpt: string | null
  duration_ms: number | null
  created_at: string | null
}

const EMPTY_FORM = {
  name: '',
  target_url: '',
  description: '',
  events: [] as string[],
  timeout_seconds: 10,
  max_attempts: 3,
  is_active: true,
}

export default function Webhooks() {
  const toast = useToast()
  const [form, setForm] = useState({ ...EMPTY_FORM })
  const [creating, setCreating] = useState(false)
  const [revealed, setRevealed] = useState<{ name: string; secret: string } | null>(null)
  const [deliveriesFor, setDeliveriesFor] = useState<Webhook | null>(null)
  const [busy, setBusy] = useState<number | null>(null)

  const hooks = useApiQuery<Webhook[]>(['webhooks'], endpoints.webhooks)
  const meta = useApiQuery<{ events: string[]; signature_header: string }>(
    ['webhook-events'],
    endpoints.webhookEvents,
  )
  const deliveries = useApiQuery<{ items: Delivery[]; total: number }>(
    ['webhook-deliveries', deliveriesFor?.webhook_id ?? 0],
    () => endpoints.webhookDeliveries(deliveriesFor!.webhook_id, { page_size: 25 }),
    { enabled: Boolean(deliveriesFor) },
  )

  const totals = (hooks.data ?? []).reduce(
    (acc, hook) => {
      acc.success += hook.success_count
      acc.failure += hook.failure_count
      if (hook.is_active) acc.active += 1
      return acc
    },
    { success: 0, failure: 0, active: 0 },
  )

  async function create() {
    setBusy(1)
    try {
      const created = await endpoints.createWebhook({
        name: form.name.trim(),
        target_url: form.target_url.trim(),
        description: form.description.trim() || null,
        events: form.events.length ? form.events : null,
        timeout_seconds: form.timeout_seconds,
        max_attempts: form.max_attempts,
        is_active: form.is_active,
      })
      setRevealed({ name: created.name, secret: created.secret ?? '' })
      setForm({ ...EMPTY_FORM })
      setCreating(false)
      await hooks.refetch()
      toast.success('Webhook created', 'Copy the signing secret now.')
    } catch (error) {
      toast.error('Could not create webhook', (error as Error).message)
    } finally {
      setBusy(null)
    }
  }

  async function testDelivery(hook: Webhook) {
    setBusy(hook.webhook_id)
    try {
      const result = await endpoints.testWebhook(hook.webhook_id, { event: hook.events[0] ?? 'run.completed' })
      const summary = result.error ?? `HTTP ${result.status_code ?? '—'} in ${result.duration_ms ?? 0} ms`
      if (result.delivered) toast.success('Test delivered', summary)
      else toast.warning('Test failed', summary)
      await hooks.refetch()
    } catch (error) {
      toast.error('Test failed', (error as Error).message)
    } finally {
      setBusy(null)
    }
  }

  async function rotate(hook: Webhook) {
    setBusy(hook.webhook_id)
    try {
      const updated = await endpoints.rotateWebhookSecret(hook.webhook_id)
      setRevealed({ name: updated.name, secret: updated.secret ?? '' })
      await hooks.refetch()
    } catch (error) {
      toast.error('Rotation failed', (error as Error).message)
    } finally {
      setBusy(null)
    }
  }

  async function remove(hook: Webhook) {
    setBusy(hook.webhook_id)
    try {
      await endpoints.deleteWebhook(hook.webhook_id)
      await hooks.refetch()
      toast.success('Webhook deleted', hook.name)
    } catch (error) {
      toast.error('Delete failed', (error as Error).message)
    } finally {
      setBusy(null)
    }
  }

  async function toggleActive(hook: Webhook) {
    try {
      await endpoints.updateWebhook(hook.webhook_id, { is_active: !hook.is_active })
      await hooks.refetch()
    } catch (error) {
      toast.error('Update failed', (error as Error).message)
    }
  }

  const columns: Column<Webhook>[] = [
    {
      key: 'name',
      header: 'Subscription',
      render: (row) => (
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <WebhookIcon className="h-4 w-4 shrink-0 text-brand" aria-hidden />
            <span className="truncate font-medium">{row.name}</span>
            {row.is_active ? (
              <Badge tone="success">active</Badge>
            ) : (
              <Badge tone="danger">disabled</Badge>
            )}
          </div>
          <p className="mt-0.5 truncate font-mono text-xs text-muted">{row.target_url}</p>
          {row.description && <p className="mt-0.5 text-xs text-muted">{row.description}</p>}
        </div>
      ),
    },
    {
      key: 'events',
      header: 'Events',
      render: (row) => (
        <div className="flex flex-wrap gap-1">
          {row.events.slice(0, 3).map((event) => (
            <Badge key={event} tone="neutral">
              {event}
            </Badge>
          ))}
          {row.events.length > 3 && <span className="text-xs text-muted">+{row.events.length - 3}</span>}
        </div>
      ),
    },
    {
      key: 'deliveries',
      header: 'Deliveries',
      align: 'right',
      render: (row) => (
        <div className="text-xs">
          <span className="text-success">{formatNumber(row.success_count)} ok</span>
          <span className="mx-1 text-muted">/</span>
          <span className={row.failure_count ? 'text-danger' : 'text-muted'}>
            {formatNumber(row.failure_count)} failed
          </span>
          {row.last_status_code && (
            <p className="mt-0.5 text-muted">last HTTP {row.last_status_code}</p>
          )}
        </div>
      ),
    },
    {
      key: 'last',
      header: 'Last activity',
      render: (row) => (
        <div className="text-xs">
          {row.last_triggered_at ? formatDateTime(row.last_triggered_at) : <span className="text-muted">never</span>}
          {row.disabled_reason && (
            <p className="mt-0.5 flex items-center gap-1 text-warning">
              <AlertTriangle className="h-3 w-3" aria-hidden />
              {row.disabled_reason}
            </p>
          )}
          {row.last_error && !row.disabled_reason && (
            <p className="mt-0.5 truncate text-danger" title={row.last_error}>
              {row.last_error}
            </p>
          )}
        </div>
      ),
    },
    {
      key: 'actions',
      header: '',
      align: 'right',
      render: (row) => (
        <div className="flex justify-end gap-1">
          <Toggle checked={row.is_active} onChange={() => void toggleActive(row)} label="Active" />
          <IconButton
            label="Send a test event"
            icon={<Send className="h-4 w-4" />}
            onClick={() => void testDelivery(row)}
            disabled={busy === row.webhook_id}
          />
          <IconButton
            label="Delivery log"
            icon={<RefreshCw className="h-4 w-4" />}
            onClick={() => setDeliveriesFor(row)}
          />
          <IconButton
            label="Rotate signing secret"
            icon={<RotateCw className="h-4 w-4" />}
            onClick={() => void rotate(row)}
          />
          <IconButton
            label="Delete webhook"
            icon={<Trash2 className="h-4 w-4" />}
            className="text-danger hover:text-danger"
            onClick={() => void remove(row)}
          />
        </div>
      ),
    },
  ]

  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Subscriptions" value={formatNumber((hooks.data ?? []).length)} icon={<WebhookIcon className="h-4 w-4" />} />
        <StatTile label="Active" value={formatNumber(totals.active)} icon={<CheckCircle2 className="h-4 w-4" />} tone="success" />
        <StatTile label="Deliveries sent" value={formatNumber(totals.success)} icon={<Send className="h-4 w-4" />} />
        <StatTile label="Failed deliveries"
            value={formatNumber(totals.failure)}
            icon={<XCircle className="h-4 w-4" />}
            tone={totals.failure ? 'danger' : 'neutral'}
          />
      </div>

      <Card>
        <CardHeader
          title="Outbound webhooks"
          subtitle="Signed, retried event delivery to your own systems"
          icon={<WebhookIcon className="h-4 w-4" />}
          action={
            <Button onClick={() => setCreating(true)} icon={<Plus className="h-4 w-4" />}>
              New webhook
            </Button>
          }
        />
        {hooks.isLoading ? (
          <LoadingState rows={3} />
        ) : hooks.isError ? (
          <ErrorState
            title="Could not load webhooks"
            message={(hooks.error as Error)?.message}
            onRetry={() => void hooks.refetch()}
          />
        ) : (hooks.data ?? []).length === 0 ? (
          <EmptyState
            icon={<WebhookIcon className="h-6 w-6" />}
            title="No webhooks yet"
            message="Create one to receive signed pipeline events in your own application."
            action={<Button icon={<Plus className="h-4 w-4" />} onClick={() => setCreating(true)}>Create the first webhook</Button>}
          />
        ) : (
          <DataTable columns={columns} rows={hooks.data ?? []} rowKey={(row) => String(row.webhook_id)} />
        )}
      </Card>

      <Modal open={creating} onClose={() => setCreating(false)} title="New webhook subscription" size="lg">
        <div className="space-y-4">
          <label className="block text-sm">
            <span className="mb-1 block font-medium">Name</span>
            <TextInput
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
              placeholder="Price monitor"
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium">Target URL</span>
            <TextInput
              value={form.target_url}
              onChange={(event) => setForm({ ...form, target_url: event.target.value })}
              placeholder="https://hooks.example.com/product-intelligence"
            />
            <span className="mt-1 block text-xs text-muted">
              Must be a public http(s) endpoint. Loopback and private addresses are rejected.
            </span>
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium">Description</span>
            <TextInput
              value={form.description}
              onChange={(event) => setForm({ ...form, description: event.target.value })}
              placeholder="Optional note"
            />
          </label>
          <div>
            <span className="mb-2 block text-sm font-medium">Events</span>
            <div className="grid gap-1.5 sm:grid-cols-2">
              {(meta.data?.events ?? []).map((event) => {
                const checked = form.events.includes(event)
                return (
                  <label key={event} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() =>
                        setForm({
                          ...form,
                          events: checked ? form.events.filter((e) => e !== event) : [...form.events, event],
                        })
                      }
                    />
                    <span className="font-mono text-xs">{event}</span>
                  </label>
                )
              })}
            </div>
            <p className="mt-2 text-xs text-muted">Leave all unchecked to subscribe to every event.</p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-sm">
              <span className="mb-1 block font-medium">Timeout (seconds)</span>
              <TextInput
                type="number"
                min={1}
                max={60}
                value={form.timeout_seconds}
                onChange={(event) => setForm({ ...form, timeout_seconds: Number(event.target.value) })}
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block font-medium">Max attempts</span>
              <Select
                value={String(form.max_attempts)}
                onChange={(event) => setForm({ ...form, max_attempts: Number(event.target.value) })}
              >
                {[1, 2, 3, 4, 5].map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </Select>
            </label>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" icon={<X className="h-4 w-4" />} onClick={() => setCreating(false)}>
              Cancel
            </Button>
            <Button
              icon={<Plus className="h-4 w-4" />}
              onClick={() => void create()}
              disabled={busy === 1 || !form.name.trim() || !form.target_url.trim()}
            >
              Create webhook
            </Button>
          </div>
        </div>
      </Modal>

      <Modal
        open={Boolean(revealed)}
        onClose={() => setRevealed(null)}
        title="Save your signing secret"
        size="md"
      >
        {revealed && (
          <div className="space-y-3">
            <p className="text-sm text-muted">
              This secret signs every payload for <strong>{revealed.name}</strong>. It is shown once and is
              never returned again.
            </p>
            <code className="block break-all rounded-lg bg-surface-2 p-3 font-mono text-xs">{revealed.secret}</code>
            <p className="text-xs text-muted">
              Verify with <code className="font-mono">{meta.data?.signature_header ?? 'X-Webhook-Signature'}</code>:
              HMAC-SHA256 over <code className="font-mono">timestamp.body</code> using this secret.
            </p>
            <div className="flex justify-end gap-2">
              <Button
                variant="secondary"
                icon={<Copy className="h-4 w-4" />}
                onClick={() => {
                  void navigator.clipboard?.writeText(revealed.secret)
                  toast.success('Copied to clipboard')
                }}
              >
                Copy
              </Button>
              <Button icon={<Check className="h-4 w-4" />} onClick={() => setRevealed(null)}>Done</Button>
            </div>
          </div>
        )}
      </Modal>

      <Modal
        open={Boolean(deliveriesFor)}
        onClose={() => setDeliveriesFor(null)}
        title={`Delivery log — ${deliveriesFor?.name ?? ''}`}
        size="lg"
      >
        {deliveries.isLoading ? (
          <LoadingState rows={3} />
        ) : (deliveries.data?.items ?? []).length === 0 ? (
          <EmptyState
            icon={<KeyRound className="h-6 w-6" />}
            title="No deliveries yet"
            message="Send a test event to see the signed payload arrive."
          />
        ) : (
          <div className="space-y-2">
            {(deliveries.data?.items ?? []).map((item) => (
              <div key={item.delivery_id} className="rounded-lg border border-line p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-mono text-xs">{item.event}</span>
                  <Badge tone={item.status === 'success' ? 'success' : 'danger'}>
                    {item.status === 'success' ? `HTTP ${item.status_code}` : (item.status ?? 'failed')}
                  </Badge>
                </div>
                <p className="mt-1 text-xs text-muted">
                  {item.created_at ? formatDateTime(item.created_at) : ''} · {String(item.attempts)} attempt
                  {item.attempts === 1 ? '' : 's'} · {item.duration_ms ?? 0} ms
                </p>
                {item.error && <p className="mt-1 break-words text-xs text-danger">{item.error}</p>}
              </div>
            ))}
          </div>
        )}
      </Modal>
    </div>
  )
}
