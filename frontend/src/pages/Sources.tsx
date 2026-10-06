import { useMemo, useState } from 'react'
import {
  AlertTriangle,
  Boxes,
  Clock,
  ExternalLink,
  Globe,
  LayoutGrid,
  Plus,
  Rows3,
  ShieldCheck,
  Table as TableIcon,
  Trash2,
} from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

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
  Segmented,
  Select,
  StatTile,
  Tabs,
  TextInput,
  Toggle,
  useToast,
  type Column,
  type Tone,
} from '@/components/ui'
import { cn } from '@/lib/cn'
import { ExportButton } from '@/components/ExportButton'
import { endpoints } from '@/lib/api'
import { useApiQuery } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
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
function SourceCard({
  row,
  onPreview,
  onToggle,
  onDelete,
  mayManage,
  busy,
}: {
  row: any
  onPreview: (code: string) => void
  onToggle: (row: any) => void
  onDelete: (code: string) => void
  mayManage: boolean
  busy: boolean
}) {
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
        {row.managed === 'database' ? (
          <Badge tone="info">added in the app</Badge>
        ) : (
          <Badge tone="neutral">bundled</Badge>
        )}
        {row.terms_allowed ? (
          <Badge tone="success">terms allowed</Badge>
        ) : (
          <Badge tone="danger">terms restricted</Badge>
        )}
        {registry.robots_respected === false ? <Badge tone="danger">robots ignored</Badge> : null}
        {registry.supports_paging ? <Badge tone="neutral">paged</Badge> : null}
        <Badge tone="neutral">
          {formatNumber(row.rate_limit_per_minute ?? 0)} req/min {'·'} {row.min_delay_seconds ?? 0}s delay
        </Badge>
      </div>

      <div>
        <div className="mb-1 flex items-center justify-between text-xs">
          <span className="text-muted">Success rate</span>
          <span className="font-semibold tabular-nums">{rate === null ? '—' : `${rate.toFixed(1)}%`}</span>
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
            {row.sync_message ? ` — ${truncate(String(row.sync_message), 120)}` : ''}
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
          {mayManage && row.managed === 'database' ? (
            <>
              <Button
                size="sm"
                variant="ghost"
                disabled={busy}
                onClick={() => onToggle(row)}
              >
                {row.enabled ? 'Disable' : 'Enable'}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                aria-label={`Delete ${row.source_code}`}
                disabled={busy}
                onClick={() => onDelete(row.source_code)}
              >
                <Trash2 className="h-3.5 w-3.5" aria-hidden />
              </Button>
            </>
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
          <span className="block truncate font-medium">{row.canonical_name || row.raw_name || '—'}</span>
          {row.raw_name && row.raw_name !== row.canonical_name ? (
            <span className="block truncate text-[11px] text-subtle" title={row.raw_name}>
              raw: {row.raw_name}
            </span>
          ) : null}
        </span>
      ),
    },
    { key: 'category', header: 'Category', hideBelow: 'sm', render: (row) => <span className="text-xs text-muted">{row.category ?? '—'}</span> },
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
      render: (row) => <span className="tabular-nums">{row.rating === null || row.rating === undefined ? '—' : Number(row.rating).toFixed(1)}</span>,
    },
    { key: 'availability', header: 'Stock', hideBelow: 'md', render: (row) => <Badge tone={statusTone(row.availability)}>{titleCase(row.availability)}</Badge> },
    {
      key: 'quality_flags',
      header: 'Quality flags',
      render: (row) => {
        const flags: string[] = Array.isArray(row.quality_flags) ? row.quality_flags : []
        if (!flags.length) return <span className="text-subtle">{'—'}</span>
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
          <span className="text-subtle">{'—'}</span>
        ),
    },
  ]

  return (
    <Modal
      open={Boolean(code)}
      onClose={onClose}
      title={code ? `Raw records — ${code}` : 'Raw records'}
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
        <LoadingState label={`Fetching records from ${code ?? 'the source'}…`} rows={4} />
      ) : (
        <div className="space-y-3">
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              ['Requested', formatNumber(data.requested ?? 0)],
              ['Returned', formatNumber(data.returned ?? 0)],
              ['HTTP calls', formatNumber(data.http_calls ?? 0)],
              ['Errors', null],
            ].map(([label, value]) => (
              <div key={label as string} className="min-w-0">
                <dt className="stat-label">{label}</dt>
                <dd
                  className={cn(
                    'mt-0.5 truncate text-sm font-medium text-ink',
                    label === 'Errors' && Number(data.errors ?? 0) > 0 && 'text-danger',
                  )}
                >
                  {value ?? formatNumber(data.errors ?? 0)}
                </dd>
              </div>
            ))}
          </dl>
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

/* ------------------------------------------------------------------ add-source modal */
const FIELD_LABELS: { key: string; label: string; hint: string }[] = [
  { key: 'name', label: 'Name', hint: 'dot path, e.g. title' },
  { key: 'price', label: 'Price', hint: 'dot path, e.g. price' },
  { key: 'category', label: 'Category', hint: 'dot path' },
  { key: 'rating', label: 'Rating', hint: 'dot path' },
  { key: 'rating_count', label: 'Rating count', hint: 'dot path' },
  { key: 'availability', label: 'Availability', hint: 'text, true/false or stock' },
  { key: 'url', label: 'Product URL', hint: 'dot path, blank uses template' },
  { key: 'image', label: 'Image URL', hint: 'dot path' },
  { key: 'brand', label: 'Brand', hint: 'dot path' },
  { key: 'description', label: 'Description', hint: 'dot path' },
]

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 32)
}

export type SourceForm = {
  code: string
  name: string
  baseUrl: string
  termsUrl: string
  licenseNote: string
  itemsPath: string
  idField: string
  fields: Record<string, string>
  pagination: string
  pageSize: string
  limitParam: string
  offsetParam: string
  pageParam: string
  perPageParam: string
  totalPath: string
  extraParams: string
  urlTemplate: string
  currency: string
  rateLimit: string
  minDelay: string
}

/**
 * Assemble the POST /sources body. Throws on invalid extra-params JSON so the
 * caller can show the error without starting the request.
 */
export function buildSourcePayload(form: SourceForm): Record<string, unknown> {
  let params: Record<string, unknown> = {}
  if (form.extraParams.trim()) {
    try {
      const parsed: unknown = JSON.parse(form.extraParams)
      if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error('must be an object')
      }
      params = parsed as Record<string, unknown>
    } catch {
      throw new Error('Extra params are not valid JSON — enter an object like {"q": "shoes"} or leave blank.')
    }
  }
  const mapped: Record<string, string> = {}
  for (const [key, value] of Object.entries(form.fields)) {
    if (value.trim()) mapped[key] = value.trim()
  }
  return {
    code: form.code,
    name: form.name.trim(),
    base_url: form.baseUrl.trim(),
    terms_url: form.termsUrl.trim() || null,
    license_note: form.licenseNote.trim() || null,
    rate_limit_per_minute: Number(form.rateLimit) || 30,
    min_delay_seconds: Number(form.minDelay) || 0,
    terms_confirmed: true,
    enabled: true,
    mapping: {
      items_path: form.itemsPath,
      id_field: form.idField,
      fields: mapped,
      pagination: {
        style: form.pagination,
        page_size: Number(form.pageSize) || 100,
        limit_param: form.limitParam,
        offset_param: form.offsetParam,
        page_param: form.pageParam,
        per_page_param: form.perPageParam,
        total_path: form.totalPath || null,
      },
      params,
      url_template: form.urlTemplate.trim() || null,
      currency: form.currency.trim().toUpperCase() || 'USD',
    },
  }
}

function AddSourceModal({ onClose, onCreated }: { onClose: () => void; onCreated: (code: string) => void }) {
  const toast = useToast()
  const presets = useApiQuery(['source-presets'], endpoints.sourcePresets, { staleTime: 300_000 })

  const [preset, setPreset] = useState('custom')
  const [name, setName] = useState('')
  const [code, setCode] = useState('')
  const [codeTouched, setCodeTouched] = useState(false)
  const [baseUrl, setBaseUrl] = useState('')
  const [termsUrl, setTermsUrl] = useState('')
  const [licenseNote, setLicenseNote] = useState('')
  const [itemsPath, setItemsPath] = useState('products')
  const [idField, setIdField] = useState('id')
  const [fields, setFields] = useState<Record<string, string>>({ name: 'title', price: 'price' })
  const [pagination, setPagination] = useState('none')
  const [pageSize, setPageSize] = useState('100')
  const [limitParam, setLimitParam] = useState('limit')
  const [offsetParam, setOffsetParam] = useState('skip')
  const [pageParam, setPageParam] = useState('page')
  const [perPageParam, setPerPageParam] = useState('per_page')
  const [totalPath, setTotalPath] = useState('')
  const [extraParams, setExtraParams] = useState('')
  const [urlTemplate, setUrlTemplate] = useState('')
  const [currency, setCurrency] = useState('USD')
  const [rateLimit, setRateLimit] = useState('30')
  const [minDelay, setMinDelay] = useState('1.0')
  const [terms, setTerms] = useState(false)
  const [check, setCheck] = useState<any | null>(null)
  const [checking, setChecking] = useState(false)
  const [saving, setSaving] = useState(false)

  const presetMap: Record<string, any> = presets.data?.presets ?? {}

  function applyPreset(key: string) {
    setPreset(key)
    const entry = presetMap[key]
    if (!entry) return
    setBaseUrl(entry.base_url ?? '')
    setTermsUrl(entry.terms_url ?? '')
    setLicenseNote(entry.license_note ?? '')
    setItemsPath(entry.items_path ?? 'products')
    setIdField(entry.id_field ?? 'id')
    setFields({ ...(entry.fields ?? {}) })
    setPagination(entry.pagination?.style ?? 'none')
    setLimitParam(entry.pagination?.limit_param ?? 'limit')
    setOffsetParam(entry.pagination?.offset_param ?? 'skip')
    setPageParam(entry.pagination?.page_param ?? 'page')
    setPerPageParam(entry.pagination?.per_page_param ?? 'per_page')
    setTotalPath(entry.pagination?.total_path ?? '')
    setExtraParams(entry.params ? JSON.stringify(entry.params) : '')
    setUrlTemplate(entry.url_template ?? '')
    if (!name) setName(entry.label ?? '')
    if (!codeTouched) setCode(slugify(entry.label ?? key))
    setCheck(null)
  }

  function markDirty() {
    setCheck(null)
  }

  const codeValid = /^[a-z0-9_]{3,32}$/.test(code)
  const canSave =
    codeValid && name.trim().length >= 3 && baseUrl.trim().length > 8 && terms && check?.allowed && !saving

  async function runCheck() {
    setChecking(true)
    try {
      const result = await endpoints.checkSource({ base_url: baseUrl.trim(), items_path: itemsPath })
      setCheck(result)
      if (result.suggested_min_delay_seconds !== null && result.suggested_min_delay_seconds !== undefined) {
        setMinDelay(String(result.suggested_min_delay_seconds))
      }
      if (!result.allowed) toast.warning('Compliance check failed', (result.reasons ?? []).join(' · ') || 'Blocked')
    } catch (error) {
      setCheck(null)
      toast.error('Compliance check failed', (error as Error).message)
    } finally {
      setChecking(false)
    }
  }

  async function save() {
    let body: Record<string, unknown>
    try {
      body = buildSourcePayload({
        code,
        name,
        baseUrl,
        termsUrl,
        licenseNote,
        itemsPath,
        idField,
        fields,
        pagination,
        pageSize,
        limitParam,
        offsetParam,
        pageParam,
        perPageParam,
        totalPath,
        extraParams,
        urlTemplate,
        currency,
        rateLimit,
        minDelay,
      })
    } catch (error) {
      toast.error('Extra params are not valid JSON', (error as Error).message)
      return
    }
    setSaving(true)
    try {
      const created = await endpoints.createSource(body)
      toast.success('Source added', `${created.name} is enabled and will join the next run.`)
      onCreated(created.source_code)
    } catch (error) {
      toast.error('Could not add the source', (error as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Add a source"
      description="Point at a JSON endpoint, prove it is compliant, map its fields. No code, no deploy."
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="secondary"
            loading={checking}
            disabled={!baseUrl.trim()}
            onClick={runCheck}
          >
            Check compliance
          </Button>
          <Button variant="primary" loading={saving} disabled={!canSave} onClick={save}>
            Save & enable
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div>
          <p className="stat-label mb-1.5">Start from a preset</p>
          <Select value={preset} onChange={(event) => applyPreset(event.target.value)}>
            <option value="custom">Custom endpoint…</option>
            {Object.entries(presetMap).map(([key, entry]: [string, any]) => (
              <option key={key} value={key}>
                {entry.label ?? key}
              </option>
            ))}
          </Select>
          {preset !== 'custom' && presetMap[preset]?.license_note ? (
            <p className="mt-1.5 text-[11px] text-subtle">{presetMap[preset].license_note}</p>
          ) : null}
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <p className="stat-label mb-1.5">Display name</p>
            <TextInput
              value={name}
              onChange={(event) => {
                setName(event.target.value)
                if (!codeTouched) setCode(slugify(event.target.value))
              }}
              placeholder="e.g. Demo Bike Shop"
            />
          </div>
          <div>
            <p className="stat-label mb-1.5">Code (unique, a-z 0-9 _)</p>
            <TextInput
              value={code}
              onChange={(event) => {
                setCodeTouched(true)
                setCode(slugify(event.target.value))
              }}
              placeholder="e.g. demo_bike_shop"
            />
            {code && !codeValid ? (
              <p className="mt-1 text-[11px] text-danger">3–32 characters: lowercase letters, digits, underscores.</p>
            ) : null}
          </div>
        </div>

        <div>
          <p className="stat-label mb-1.5">JSON endpoint URL</p>
          <TextInput
            value={baseUrl}
            onChange={(event) => {
              setBaseUrl(event.target.value)
              markDirty()
            }}
            placeholder="https://…/products.json"
            inputMode="url"
          />
          <p className="mt-1 text-[11px] text-subtle">
            Public http(s) only — private, loopback and link-local addresses are refused (SSRF guard).
          </p>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <p className="stat-label mb-1.5">Terms URL (optional)</p>
            <TextInput value={termsUrl} onChange={(event) => setTermsUrl(event.target.value)} placeholder="https://…/terms" />
          </div>
          <div>
            <p className="stat-label mb-1.5">License note (optional)</p>
            <TextInput value={licenseNote} onChange={(event) => setLicenseNote(event.target.value)} placeholder="e.g. ODbL, attribution required" />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="col-span-1">
            <p className="stat-label mb-1.5">Items path</p>
            <TextInput
              value={itemsPath}
              onChange={(event) => {
                setItemsPath(event.target.value)
                markDirty()
              }}
              placeholder="products (blank = root)"
            />
          </div>
          <div className="col-span-1">
            <p className="stat-label mb-1.5">ID field</p>
            <TextInput value={idField} onChange={(event) => setIdField(event.target.value)} placeholder="id" />
          </div>
          <div className="col-span-1">
            <p className="stat-label mb-1.5">Currency</p>
            <TextInput value={currency} onChange={(event) => setCurrency(event.target.value)} placeholder="USD" maxLength={3} />
          </div>
          <div className="col-span-1">
            <p className="stat-label mb-1.5">Page size</p>
            <TextInput value={pageSize} onChange={(event) => setPageSize(event.target.value)} inputMode="numeric" />
          </div>
        </div>

        <div>
          <p className="stat-label mb-1.5">Field mapping (dot paths, blank = unmapped)</p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {FIELD_LABELS.map((field) => (
              <label key={field.key} className="block">
                <span className="mb-1 flex items-baseline justify-between text-[11px]">
                  <span className="font-medium text-ink">{field.label}</span>
                  <span className="text-subtle">{field.hint}</span>
                </span>
                <TextInput
                  value={fields[field.key] ?? ''}
                  onChange={(event) => setFields((current) => ({ ...current, [field.key]: event.target.value }))}
                  placeholder="—"
                />
              </label>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <p className="stat-label mb-1.5">Pagination</p>
            <Segmented
              options={[
                { id: 'none', label: 'Single shot' },
                { id: 'skip_limit', label: 'Limit + offset' },
                { id: 'page_number', label: 'Page number' },
              ]}
              value={pagination}
              onChange={setPagination}
            />
          </div>
          <div>
            <p className="stat-label mb-1.5">Product URL template (optional)</p>
            <TextInput
              value={urlTemplate}
              onChange={(event) => setUrlTemplate(event.target.value)}
              placeholder="{origin}/products/{handle}"
            />
          </div>
        </div>

        {pagination !== 'none' ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {pagination === 'skip_limit' ? (
              <>
                <div>
                  <p className="stat-label mb-1.5">Limit param</p>
                  <TextInput value={limitParam} onChange={(event) => setLimitParam(event.target.value)} />
                </div>
                <div>
                  <p className="stat-label mb-1.5">Offset param</p>
                  <TextInput value={offsetParam} onChange={(event) => setOffsetParam(event.target.value)} />
                </div>
              </>
            ) : (
              <>
                <div>
                  <p className="stat-label mb-1.5">Page param</p>
                  <TextInput value={pageParam} onChange={(event) => setPageParam(event.target.value)} />
                </div>
                <div>
                  <p className="stat-label mb-1.5">Per-page param</p>
                  <TextInput value={perPageParam} onChange={(event) => setPerPageParam(event.target.value)} />
                </div>
              </>
            )}
            <div>
              <p className="stat-label mb-1.5">Total path (optional)</p>
              <TextInput value={totalPath} onChange={(event) => setTotalPath(event.target.value)} placeholder="total" />
            </div>
            <div>
              <p className="stat-label mb-1.5">Extra params (JSON)</p>
              <TextInput value={extraParams} onChange={(event) => setExtraParams(event.target.value)} placeholder='{"q":"shoes"}' />
            </div>
          </div>
        ) : (
          <div>
            <p className="stat-label mb-1.5">Extra query params (JSON, optional)</p>
            <TextInput value={extraParams} onChange={(event) => setExtraParams(event.target.value)} placeholder='{"q":"shoes"}' />
          </div>
        )}

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <p className="stat-label mb-1.5">Rate limit (requests/minute)</p>
            <TextInput value={rateLimit} onChange={(event) => setRateLimit(event.target.value)} inputMode="numeric" />
          </div>
          <div>
            <p className="stat-label mb-1.5">Minimum delay (seconds)</p>
            <TextInput value={minDelay} onChange={(event) => setMinDelay(event.target.value)} inputMode="decimal" />
          </div>
        </div>

        <Toggle
          checked={terms}
          onChange={setTerms}
          label="Terms permit automated access"
          description="I confirm this endpoint's terms allow polling. Blocked sources are rejected regardless."
        />

        {check ? (
          <div className={cn('rounded-lg border p-3', check.allowed ? 'border-success/40 bg-success-soft' : 'border-danger/40 bg-danger-soft')}>
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={check.allowed ? 'success' : 'danger'}>{check.allowed ? 'allowed' : 'blocked'}</Badge>
              <span className="font-mono text-[11px] text-muted">{check.robots?.rule}</span>
              {check.shape?.ok ? (
                <span className="text-[11px] text-muted">
                  {formatNumber(check.shape.item_count ?? 0)} item(s) at <code className="font-mono">{itemsPath || '(root)'}</code>
                </span>
              ) : (
                <span className="text-[11px] text-danger">{check.shape?.error}</span>
              )}
            </div>
            {(check.shape?.item_keys ?? []).length ? (
              <div className="mt-2 flex flex-wrap gap-1">
                {(check.shape.item_keys as string[]).slice(0, 14).map((key) => (
                  <button
                    key={key}
                    type="button"
                    title="Use as the name field"
                    onClick={() => setFields((current) => ({ ...current, name: key }))}
                    className="rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[10px] text-muted hover:border-brand-500 hover:text-ink"
                  >
                    {key}
                  </button>
                ))}
              </div>
            ) : null}
            {(check.reasons ?? []).length ? (
              <ul className="mt-2 space-y-0.5 text-[11px] text-danger">
                {(check.reasons as string[]).map((reason) => (
                  <li key={reason}>· {reason}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
      </div>
    </Modal>
  )
}

/* ------------------------------------------------------------------ page */
export default function Sources() {
  const [view, setView] = useState('cards')
  const [previewCode, setPreviewCode] = useState<string | null>(null)
  const [showAdd, setShowAdd] = useState(false)
  const [deleteCode, setDeleteCode] = useState<string | null>(null)
  const toast = useToast()
  const queryClient = useQueryClient()
  const { can } = useAuth()
  const mayManage = can('manage_sources')

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

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['sources'] })
    void queryClient.invalidateQueries({ queryKey: ['pipeline-source-status'] })
  }

  const toggleSource = useMutation({
    mutationFn: (row: any) => endpoints.updateSource(row.source_code, { enabled: !row.enabled }),
    onSuccess: () => {
      refresh()
      toast.success('Source updated')
    },
    onError: (error) => toast.error('Could not update the source', (error as Error).message),
  })

  const deleteSource = useMutation({
    mutationFn: (code: string) => endpoints.deleteSource(code),
    onSuccess: () => {
      refresh()
      setDeleteCode(null)
      toast.success('Source deleted')
    },
    onError: (error) => toast.error('Could not delete the source', (error as Error).message),
  })
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
                ? '—'
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
    {
      key: 'manage',
      header: '',
      align: 'right',
      hideBelow: 'md',
      render: (row) =>
        mayManage && row.managed === 'database' ? (
          <span className="flex items-center justify-end gap-1" onClick={(event) => event.stopPropagation()}>
            <button
              onClick={() => toggleSource.mutate(row)}
              className="link text-xs"
            >
              {row.enabled ? 'Disable' : 'Enable'}
            </button>
            <button
              onClick={() => setDeleteCode(row.source_code)}
              className="link text-xs text-danger"
              aria-label={`Delete ${row.source_code}`}
            >
              Delete
            </button>
          </span>
        ) : null,
    },
  ]

  if (status.isError && !status.data) {
    return <ErrorState message={(status.error as Error)?.message} onRetry={() => status.refetch()} />
  }
  if (status.isLoading && !status.data) {
    return <LoadingState label={'Loading ingestion sources…'} rows={6} />
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
                    {robots.data?.user_agent ?? '—'}
                  </span>
                ),
              },
              {
                label: 'robots.txt cache TTL',
                value: robots.data?.ttl_seconds ? formatDuration(Number(robots.data.ttl_seconds) * 1000) : '—',
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
                {decided
                  ? `${formatNumber(allowed)} allowed · ${formatNumber(blocked)} refused by robots.txt and never sent upstream`
                  : 'No robots.txt decision has been taken yet.'}
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
          value={totals.success === null ? '—' : `${totals.success.toFixed(1)}%`}
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
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Tabs
            active={view}
            onChange={setView}
            tabs={[
              { id: 'cards', label: 'Cards', count: merged.length, icon: <LayoutGrid className="h-4 w-4" /> },
              { id: 'table', label: 'Table', count: merged.length, icon: <Rows3 className="h-4 w-4" /> },
            ]}
          />
          {mayManage ? (
            <Button size="sm" variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => setShowAdd(true)}>
              Add source
            </Button>
          ) : null}
          <ExportButton dataset="sources" />
        </div>

        {status.isError ? (
          <ErrorState message={(status.error as Error)?.message} onRetry={() => status.refetch()} />
        ) : !merged.length ? (          <Card>
            <EmptyState
              title={totals.registered ? 'No source has reported yet' : 'No ingestion source is registered'}
              message={
                totals.registered
                  ? 'The registry is populated but the warehouse has no source dimension rows. Run the pipeline to collect products.'
                  : 'The source registry is empty, so no run can collect products.'
              }
              icon={<Boxes className="h-8 w-8" />}
            />
          </Card>
        ) : view === 'cards' ? (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 2xl:grid-cols-3">
            {merged.map((row: any) => (
              <SourceCard
                key={row.source_code}
                row={row}
                onPreview={setPreviewCode}
                onToggle={(target) => toggleSource.mutate(target)}
                onDelete={setDeleteCode}
                mayManage={mayManage}
                busy={toggleSource.isPending || deleteSource.isPending}
              />
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
      {showAdd ? (
        <AddSourceModal
          onClose={() => setShowAdd(false)}
          onCreated={(code) => {
            setShowAdd(false)
            refresh()
            setPreviewCode(code)
          }}
        />
      ) : null}
      <Modal
        open={Boolean(deleteCode)}
        onClose={() => setDeleteCode(null)}
        title="Delete this source?"
        description="Only sources that never ran can be deleted. Anything with history must be disabled instead."
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeleteCode(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={deleteSource.isPending}
              onClick={() => deleteCode && deleteSource.mutate(deleteCode)}
            >
              Delete
            </Button>
          </>
        }
      >
        <p className="text-sm text-muted">
          <code className="rounded bg-surface-3 px-1 font-mono text-xs">{deleteCode}</code> will be removed
          permanently. Warehouse records already collected stay untouched.
        </p>
      </Modal>
    </div>
  )
}
