import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  Building2,
  Copy,
  Download,
  ExternalLink,
  Fingerprint,
  GitCompare,
  History,
  Package,
  Star,
  Tag,
} from 'lucide-react'
import { useMutation } from '@tanstack/react-query'

import { AreaTrend, LineTrend } from '@/components/charts'
import {
  Badge,
  Button,
  Card,
  CardHeader,
  DataTable,
  DeltaPill,
  EmptyState,
  ErrorState,
  KeyValue,
  LoadingState,
  StatTile,
  Tabs,
  useToast,
} from '@/components/ui'
import { downloadBinary, endpoints } from '@/lib/api'
import { useApiQuery } from '@/hooks/useApi'
import {
  formatAvailability,
  formatDate,
  formatDateTime,
  formatNumber,
  formatPrice,
  formatRelative,
  statusTone,
  titleCase,
} from '@/lib/format'

export default function ProductDetail() {
  const { id } = useParams()
  const productId = Number(id)
  const [tab, setTab] = useState('history')

  const product = useApiQuery(['product', productId], () => endpoints.product(productId), { enabled: Number.isFinite(productId) })
  const history = useApiQuery(['product-history', productId], () => endpoints.productHistory(productId, 600), {
    enabled: Number.isFinite(productId),
  })
  const duplicates = useApiQuery(['product-duplicates', productId], () => endpoints.productDuplicates(productId), {
    enabled: Number.isFinite(productId),
  })
  const toast = useToast()
  const exportHistory = useMutation({
    mutationFn: () => downloadBinary(`/products/${productId}/history.csv`, {}, `product-${productId}-history.csv`),
    onSuccess: () => toast.success('History exported', 'Every snapshot with USD prices and changes.'),
    onError: (error: Error) => toast.error('Could not export the history', error.message),
  })

  if (!Number.isFinite(productId)) {
    return <ErrorState title="Invalid product id" message="The URL does not contain a numeric product id." />
  }
  if (product.isError) {
    return <ErrorState title="Product not found" message={(product.error as Error)?.message} onRetry={() => product.refetch()} />
  }
  if (product.isLoading && !product.data) return <LoadingState label="Loading product…" rows={6} />

  const data = product.data ?? {}
  const availabilityInfo = formatAvailability(data.availability)
  const points = (history.data?.history ?? []).map((row: any) => ({
    ...row,
    label: formatDate(row.full_date ?? row.captured_at),
    price: row.price_usd !== null && row.price_usd !== undefined ? Number(row.price_usd) : null,
    native: row.price !== null && row.price !== undefined ? Number(row.price) : null,
    rating: row.rating !== null && row.rating !== undefined ? Number(row.rating) : null,
  }))

  const catalogRows = data.catalog ?? []
  const duplicateRows = duplicates.data?.candidates ?? []

  return (
    <div className="space-y-4">
      {/* ------------------------------------------------------------- header */}
      <div className="flex flex-wrap items-start gap-3">
        <Link to="/products" className="btn btn-ghost h-9 w-9 !p-0" aria-label="Back to products">
          <ArrowLeft className="h-4 w-4" />
        </Link>
        {data.image_url ? (
          <img
            src={data.image_url}
            alt=""
            className="h-16 w-16 shrink-0 rounded-xl border border-line bg-surface object-contain p-1.5"
            onError={(event) => {
              ;(event.currentTarget as HTMLImageElement).style.display = 'none'
            }}
          />
        ) : (
          <span className="flex h-16 w-16 shrink-0 items-center justify-center rounded-xl border border-line bg-surface text-subtle">
            <Package className="h-6 w-6" aria-hidden />
          </span>
        )}
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-lg font-semibold text-ink">{data.canonical_name}</h2>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            {data.brand ? <Badge tone="neutral">{data.brand}</Badge> : null}
            {data.category_path ? <Badge tone="brand">{data.category_path}</Badge> : null}
            <Badge tone={availabilityInfo.tone === 'info' ? 'info' : availabilityInfo.tone}>{availabilityInfo.label}</Badge>
            <Badge tone={data.is_active ? 'success' : 'danger'} dot>
              {data.is_active ? 'active' : 'inactive'}
            </Badge>
            {data.match_strategy ? <Badge tone="info">matched: {data.match_strategy}</Badge> : null}
          </div>
        </div>
        <div className="flex shrink-0 gap-2">
          {data.product_url ? (
            <Button size="sm" variant="secondary" icon={<ExternalLink className="h-4 w-4" />} onClick={() => window.open(data.product_url, '_blank', 'noopener')}>
              Source page
            </Button>
          ) : null}
          <Button size="sm" variant="ghost" icon={<Copy className="h-4 w-4" />} onClick={() => navigator.clipboard?.writeText(String(data.product_url ?? data.canonical_name))}>
            Copy link
          </Button>
        </div>
      </div>

      {/* ------------------------------------------------------------- KPIs */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Current price"
          value={formatPrice(data.price_usd ?? data.current_price, data.currency ?? 'USD')}
          hint={`Listed in ${data.currency ?? 'USD'}`}
          icon={<Package className="h-4 w-4" />}
        />
        <StatTile
          label="Last movement"
          value={<DeltaPill value={data.price_change_pct} digits={2} />}
          hint={data.price_change_abs ? `${Number(data.price_change_abs) > 0 ? '+' : ''}${Number(data.price_change_abs).toFixed(2)} absolute` : 'No movement recorded'}
          icon={<History className="h-4 w-4" />}
          tone={Number(data.price_change_pct ?? 0) < 0 ? 'success' : 'warning'}
        />
        <StatTile
          label="Rating"
          value={data.rating ? Number(data.rating).toFixed(2) : '—'}
          hint={data.rating_count ? `${formatNumber(data.rating_count)} reviews` : 'No review count published'}
          icon={<Star className="h-4 w-4" />}
          tone="info"
        />
        <StatTile
          label="Observations"
          value={formatNumber(data.observation_count ?? 0)}
          hint={`First seen ${formatRelative(data.first_seen_at)} · last ${formatRelative(data.last_seen_at)}`}
          icon={<History className="h-4 w-4" />}
          tone="neutral"
        />
      </div>

      {/* ------------------------------------------------------------- charts */}
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title="Price history (USD)" subtitle="Normalised to USD with the offline FX table" icon={<History className="h-4 w-4" />} />
          {points.length > 1 ? (
            <AreaTrend
              data={points}
              xKey="label"
              series={[
                { key: 'price', label: 'Price (USD)' },
                { key: 'rating', label: 'Rating', color: 'var(--chart-4)' },
              ]}
              height={280}
              formatY="currency"
            />
          ) : (
            <EmptyState title="Not enough history" message="This product has been observed only once." />
          )}
        </Card>

        <Card>
          <CardHeader title="Identity" subtitle="Deduplication evidence" icon={<Fingerprint className="h-4 w-4" />} />
          <KeyValue
            items={[
              { label: 'Product id', value: <span className="font-mono text-xs">#{data.product_id}</span> },
              { label: 'Source', value: data.source_code ?? '—' },
              { label: 'Source id', value: <span className="font-mono text-xs break-all">{data.source_product_id ?? '—'}</span> },
              { label: 'Fingerprint', value: <span className="font-mono text-[10px] break-all">{data.fingerprint ?? '—'}</span> },
              { label: 'Match strategy', value: data.match_strategy ?? '—' },
              { label: 'Match score', value: data.match_score !== null && data.match_score !== undefined ? Number(data.match_score).toFixed(4) : '—' },
              { label: 'Discount', value: data.discount_pct ? `${Number(data.discount_pct).toFixed(1)}%` : '—' },
              { label: 'Availability', value: availabilityInfo.label },
            ]}
          />
        </Card>
      </div>

      {/* ------------------------------------------------------------- tabs */}
      <Card padded={false}>
        <div className="flex flex-wrap items-center justify-between gap-2 px-4 pt-4 sm:px-5">
          <Tabs
            active={tab}
            onChange={setTab}
            tabs={[
              { id: 'history', label: 'Snapshots', count: points.length, icon: <History className="h-4 w-4" /> },
              { id: 'changes', label: 'Price changes', count: data.changes?.length ?? 0 },
              { id: 'events', label: 'Lifecycle', count: data.events?.length ?? 0 },
              { id: 'duplicates', label: 'Duplicates', count: duplicateRows.length, icon: <GitCompare className="h-4 w-4" /> },
              { id: 'catalog', label: 'Catalog', count: catalogRows.length, icon: <Building2 className="h-4 w-4" /> },
            ]}
          />
          <Button
            size="sm"
            variant="ghost"
            icon={<Download className="h-4 w-4" />}
            loading={exportHistory.isPending}
            disabled={!points.length}
            onClick={() => exportHistory.mutate()}
            title="Download every snapshot as CSV"
          >
            Export CSV
          </Button>
        </div>

        {tab === 'history' ? (
          <DataTable
            rows={points}
            rowKey={(row: any) => String(row.snapshot_id)}
            loading={history.isFetching}
            emptyMessage="No snapshots recorded"
            columns={[
              { key: 'date', header: 'Date', render: (row: any) => formatDate(row.full_date ?? row.captured_at) },
              { key: 'captured', header: 'Captured', hideBelow: 'md', render: (row: any) => formatDateTime(row.captured_at) },
              { key: 'price', header: 'Price', align: 'right', render: (row: any) => formatPrice(row.price, row.currency) },
              { key: 'usd', header: 'USD', align: 'right', render: (row: any) => formatPrice(row.price_usd) },
              { key: 'rating', header: 'Rating', align: 'center', hideBelow: 'sm', render: (row: any) => (row.rating !== null ? Number(row.rating).toFixed(1) : '—') },
              { key: 'availability', header: 'Availability', hideBelow: 'lg', render: (row: any) => {
                const info = formatAvailability(row.availability)
                return <Badge tone={info.tone === 'info' ? 'info' : info.tone}>{info.label}</Badge>
              } },
              { key: 'first', header: 'First', align: 'center', hideBelow: 'xl', render: (row: any) => (row.is_first_sighting ? <Badge tone="success">yes</Badge> : <span className="text-subtle">no</span>) },
              {
                key: 'change',
                header: 'Change',
                align: 'right',
                render: (row: any) => <DeltaPill value={row.price_change_pct} />,
              },
            ]}
          />
        ) : null}

        {tab === 'changes' ? (
          <DataTable
            rows={data.changes ?? []}
            rowKey={(row: any) => String(row.change_id)}
            emptyMessage="No price change has been recorded for this product"
            columns={[
              { key: 'date', header: 'Detected', render: (row: any) => formatDate(row.full_date ?? row.detected_at) },
              { key: 'from', header: 'From', align: 'right', render: (row: any) => formatPrice(row.previous_price) },
              { key: 'to', header: 'To', align: 'right', render: (row: any) => formatPrice(row.new_price) },
              { key: 'abs', header: 'Absolute', align: 'right', hideBelow: 'sm', render: (row: any) => (row.change_abs ? Number(row.change_abs).toFixed(2) : '—') },
              { key: 'pct', header: 'Change', align: 'right', render: (row: any) => <DeltaPill value={row.change_pct} /> },
              { key: 'band', header: 'Band', align: 'center', hideBelow: 'md', render: (row: any) => <Badge tone="neutral">{row.magnitude_band ?? '—'}</Badge> },
            ]}
          />
        ) : null}

        {tab === 'events' ? (
          <DataTable
            rows={data.events ?? []}
            rowKey={(row: any, index) => `${row.event_type}-${index}`}
            emptyMessage="No lifecycle events recorded"
            columns={[
              { key: 'date', header: 'Detected', render: (row: any) => formatDate(row.full_date ?? row.detected_at) },
              { key: 'type', header: 'Event', render: (row: any) => (
                <Badge tone={row.event_type === 'removed' ? 'danger' : row.event_type === 'new' ? 'success' : row.event_type === 'category_changed' ? 'warning' : 'info'}>
                  {titleCase(row.event_type)}
                </Badge>
              ) },
              { key: 'old', header: 'Old', render: (row: any) => <span className="text-xs text-muted">{row.old_value ?? '—'}</span> },
              { key: 'new', header: 'New', render: (row: any) => <span className="text-xs font-medium">{row.new_value ?? '—'}</span> },
              { key: 'severity', header: 'Severity', align: 'center', hideBelow: 'sm', render: (row: any) => <Badge tone={row.severity === 'warning' ? 'warning' : 'neutral'}>{titleCase(row.severity ?? 'info')}</Badge> },
            ]}
          />
        ) : null}

        {tab === 'duplicates' ? (
          duplicateRows.length ? (
            <DataTable
              rows={duplicateRows}
              rowKey={(row: any) => String(row.product_id)}
              emptyMessage="No similar products"
              columns={[
                { key: 'name', header: 'Candidate', render: (row: any) => <Link to={`/products/${row.product_id}`} className="font-medium">{row.name}</Link> },
                {
                  key: 'score',
                  header: 'Similarity',
                  align: 'right',
                  render: (row: any) => (
                    <span className="flex items-center justify-end gap-2">
                      <span className="h-1.5 w-24 overflow-hidden rounded-full bg-surface-3">
                        <span className="block h-full rounded-full bg-brand-500" style={{ width: `${Math.round(row.score * 100)}%` }} />
                      </span>
                      <span className="w-14 text-right font-mono text-xs tabular-nums">{row.score.toFixed(4)}</span>
                    </span>
                  ),
                },
                {
                  key: 'parts',
                  header: 'Components',
                  hideBelow: 'md',
                  render: (row: any) => (
                    <span className="flex flex-wrap gap-1">
                      {Object.entries(row.parts ?? {})
                        .slice(0, 4)
                        .map(([key, value]) => (
                          <span key={key} className="rounded bg-surface-3 px-1.5 py-0.5 font-mono text-[10px] text-muted">
                            {key}: {Number(value).toFixed(2)}
                          </span>
                        ))}
                    </span>
                  ),
                },
                {
                  key: 'verdict',
                  header: 'Verdict',
                  align: 'center',
                  render: (row: any) => (
                    <Badge tone={row.score >= 0.9 ? 'danger' : row.score >= 0.8 ? 'warning' : 'neutral'}>
                      {row.score >= 0.9 ? 'duplicate' : row.score >= 0.8 ? 'review' : 'distinct'}
                    </Badge>
                  ),
                },
              ]}
            />
          ) : (
            <EmptyState title="No duplicate candidates" message="The deduplicator found nothing above 0.55 similarity." icon={<GitCompare className="h-7 w-7" />} />
          )
        ) : null}

        {tab === 'catalog' ? (
          catalogRows.length ? (
            <DataTable
              rows={catalogRows}
              rowKey={(row: any) => String(row.catalog_sku)}
              emptyMessage="Not linked to an internal catalog SKU"
              columns={[
                { key: 'sku', header: 'SKU', render: (row: any) => <span className="font-mono text-xs">{row.catalog_sku}</span> },
                { key: 'name', header: 'Catalog name', render: (row: any) => <span className="block max-w-[18rem] truncate">{row.catalog_name}</span> },
                { key: 'price', header: 'Catalog price', align: 'right', render: (row: any) => formatPrice(row.catalog_price) },
                { key: 'gap', header: 'Gap %', align: 'right', render: (row: any) => <DeltaPill value={row.price_gap_pct} /> },
                { key: 'status', header: 'Status', align: 'center', render: (row: any) => <Badge tone={statusTone(row.match_status)}>{titleCase(row.match_status ?? 'unknown')}</Badge> },
                { key: 'strategy', header: 'Strategy', hideBelow: 'md', render: (row: any) => <Badge tone="neutral">{row.match_strategy ?? '—'}</Badge> },
                { key: 'sim', header: 'Similarity', align: 'right', hideBelow: 'sm', render: (row: any) => (row.similarity_score !== null ? Number(row.similarity_score).toFixed(3) : '—') },
              ]}
            />
          ) : (
            <EmptyState title="No catalog match" message="This scraped product has not been matched to an internal SKU yet." icon={<Building2 className="h-7 w-7" />} />
          )
        ) : null}
      </Card>

      {/* ------------------------------------------------------------- description */}
      {data.description ? (
        <Card>
          <CardHeader title="Description" subtitle="Cleaned upstream description" icon={<Tag className="h-4 w-4" />} />
          <p className="text-sm leading-relaxed text-muted">{data.description}</p>
        </Card>
      ) : null}

      {points.length > 1 ? (
        <Card>
          <CardHeader title="Rating trend" subtitle="Normalised to a 0-5 scale" icon={<Star className="h-4 w-4" />} />
          <LineTrend data={points} xKey="label" series={[{ key: 'rating', label: 'Rating', color: 'var(--chart-4)' }]} height={200} />
        </Card>
      ) : null}
    </div>
  )
}