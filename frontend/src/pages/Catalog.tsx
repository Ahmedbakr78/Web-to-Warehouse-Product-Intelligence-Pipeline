import { useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Building2, FileDown, GitCompare, Play, RefreshCw, TrendingDown, TrendingUp, Upload } from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { BarSeries, DonutChart } from '@/components/charts'
import {
  Badge,
  Button,
  Card,
  CardHeader,
  DataTable,
  DeltaPill,
  EmptyState,
  ErrorState,
  LoadingState,
  Modal,
  Pagination,
  ProgressBar,
  SearchInput,
  Select,
  StatTile,
  Tabs,
  useToast,
} from '@/components/ui'
import { downloadBinary, endpoints, uploadCatalogCsv } from '@/lib/api'
import { useApiQuery } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { useDebounce } from '@/hooks/useDebounce'
import { formatCompact, formatDateTime, formatNumber, formatPrice, formatRelative, statusTone, titleCase } from '@/lib/format'

export default function Catalog() {
  const [tab, setTab] = useState('reconciliation')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  const [search, setSearch] = useState('')
  const [matchStatus, setMatchStatus] = useState('')
  const [onlyMismatches, setOnlyMismatches] = useState(false)
  const [direction, setDirection] = useState('')
  const queryClient = useQueryClient()
  const toast = useToast()
  const { can } = useAuth()
  const debouncedSearch = useDebounce(search, 300)

  const summary = useApiQuery(['catalog-summary'], () => endpoints.catalogSummary())
  const opportunities = useApiQuery(['catalog-opportunities'], () => endpoints.catalogOpportunities(20))
  const catalogProducts = useApiQuery(['catalog-skus'], () => endpoints.catalogProducts({ page: 1, page_size: 200 }))
  const runs = useApiQuery(['runs-min'], () => endpoints.runs({ page: 1, page_size: 25 }))

  const params = useMemo(
    () => ({
      page,
      page_size: pageSize,
      match_status: matchStatus || undefined,
      only_mismatches: onlyMismatches || undefined,
    }),
    [page, pageSize, matchStatus, onlyMismatches],
  )
  const reconciliation = useApiQuery(['catalog-reconciliation', params], () => endpoints.catalogReconciliation(params))

  const trigger = useMutation({
    mutationFn: () => endpoints.triggerRunSync({ limit_per_source: 30, trigger: 'dashboard' }),
    onSuccess: (result) => {
      toast.success('Pipeline run completed', `${result?.status} · ${result?.counters?.snapshots_inserted ?? 0} snapshots`)
      void queryClient.invalidateQueries()
    },
    onError: (error: Error) => toast.error('Pipeline run failed', error.message),
  })

  const fileRef = useRef<HTMLInputElement>(null)
  const catalogImport = useMutation({
    mutationFn: (file: File) => uploadCatalogCsv(file),
    onSuccess: (result) => {
      toast.success('Catalog imported', `${result.created} created · ${result.updated} updated`)
      void queryClient.invalidateQueries()
    },
    onError: (error: Error) => toast.error('Catalog import failed', error.message),
  })
  const downloadTemplate = useMutation({
    mutationFn: () => downloadBinary('/catalog/template', {}, 'catalog-template.csv'),
    onSuccess: () => toast.success('Template downloaded', 'Fill it in and import it back above.'),
    onError: (error: Error) => toast.error('Could not download the template', error.message),
  })
  const exportSkus = useMutation({
    mutationFn: () => downloadBinary('/catalog/export.csv', {}, 'catalog-export.csv'),
    onSuccess: () => toast.success('Catalog exported', 'Every SKU with the import-compatible columns.'),
    onError: (error: Error) => toast.error('Could not export the catalog', error.message),
  })

  const rows = reconciliation.data?.items ?? []
  const filtered = debouncedSearch
    ? rows.filter((row: any) =>
        `${row.catalog_name ?? ''} ${row.scraped_name ?? ''} ${row.catalog_sku ?? ''} ${row.catalog_brand ?? ''}`
          .toLowerCase()
          .includes(debouncedSearch.toLowerCase()),
      )
    : rows

  const totals = summary.data?.totals ?? {}
  const matchRate = Number(totals.total ?? 0) > 0 ? (Number(totals.matched ?? 0) / Number(totals.total)) * 100 : 0
  const opportunityRows = opportunities.data ?? []

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Tabs
          active={tab}
          onChange={setTab}
          tabs={[
            { id: 'reconciliation', label: 'Reconciliation', icon: <GitCompare className="h-4 w-4" /> },
            { id: 'opportunities', label: 'Pricing opportunities', count: opportunityRows.length, icon: <TrendingUp className="h-4 w-4" /> },
            { id: 'skus', label: 'Internal SKUs', count: catalogProducts.data?.total ?? 0, icon: <Building2 className="h-4 w-4" /> },
          ]}
        />
        <div className="flex items-center gap-2">
          {runs.data?.items?.[0] ? (
            <span className="text-[11px] text-subtle">
              Last reconciliation {formatRelative(runs.data.items[0].started_at)} ({runs.data.items[0].run_id?.slice(0, 8)})
            </span>
          ) : null}
          <input
            ref={fileRef}
            type="file"
            accept=".csv,text/csv"
            className="hidden"
            aria-label="Upload catalog CSV"
            onChange={(event) => {
              const file = event.target.files?.[0]
              event.target.value = ''
              if (file) catalogImport.mutate(file)
            }}
          />
          <Button
            size="sm"
            variant="ghost"
            icon={<FileDown className="h-4 w-4" />}
            loading={downloadTemplate.isPending}
            onClick={() => downloadTemplate.mutate()}
            title="Download the CSV template with header and examples"
          >
            Template
          </Button>
          <Button
            size="sm"
            variant="ghost"
            icon={<FileDown className="h-4 w-4" />}
            loading={exportSkus.isPending}
            onClick={() => exportSkus.mutate()}
            title="Download every SKU — same columns as the import template"
          >
            Export CSV
          </Button>
          {can('write') ? (
            <Button
              size="sm"
              variant="secondary"
              icon={<Upload className="h-4 w-4" />}
              loading={catalogImport.isPending}
              onClick={() => fileRef.current?.click()}
              title="Bulk upsert SKUs from a CSV file (5 MB / 5,000 rows)"
            >
              Import CSV
            </Button>
          ) : null}
          {can('run_pipeline') ? (
            <Button
              size="sm"
              variant="primary"
              icon={<Play className="h-4 w-4" />}
              loading={trigger.isPending}
              onClick={() => trigger.mutate()}
            >
              Re-run pipeline
            </Button>
          ) : null}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Match rate"
          value={`${matchRate.toFixed(1)}%`}
          hint={`${formatNumber(totals.matched ?? 0)} of ${formatNumber(totals.total ?? 0)} SKUs matched`}
          icon={<GitCompare className="h-4 w-4" />}
          tone={matchRate >= 60 ? 'success' : matchRate >= 30 ? 'warning' : 'danger'}
        >
        </StatTile>
        <StatTile
          label="Price mismatches"
          value={formatNumber(totals.price_mismatches ?? 0)}
          hint="Gap of 1% or more versus our list price"
          icon={<TrendingUp className="h-4 w-4" />}
          tone="warning"
        />
        <StatTile
          label="Average similarity"
          value={totals.avg_similarity !== null && totals.avg_similarity !== undefined ? Number(totals.avg_similarity).toFixed(3) : '—'}
          hint="Mean fuzzy match score"
          icon={<GitCompare className="h-4 w-4" />}
          tone="info"
        />
        <StatTile
          label="Average price gap"
          value={totals.avg_price_gap_pct !== null && totals.avg_price_gap_pct !== undefined ? `${Number(totals.avg_price_gap_pct).toFixed(2)}%` : '—'}
          hint="Positive = we are dearer than the market"
          icon={<TrendingDown className="h-4 w-4" />}
          tone="neutral"
        />
      </div>

      {tab === 'reconciliation' ? (
        <Card padded={false}>
          <div className="space-y-3 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <SearchInput value={search} onChange={(value) => { setSearch(value); setPage(1) }} placeholder="Search SKU or product…" className="min-w-[15rem] flex-1" />
              <Select value={matchStatus} onChange={(event) => { setMatchStatus(event.target.value); setPage(1) }} aria-label="Match status" className="w-36">
                <option value="">All statuses</option>
                <option value="matched">Matched</option>
                <option value="unmatched">Unmatched</option>
              </Select>
              <Button size="sm" variant={onlyMismatches ? 'primary' : 'secondary'} onClick={() => { setOnlyMismatches((value) => !value); setPage(1) }}>
                Price mismatches only
              </Button>
              <div className="ml-auto text-xs text-subtle">{formatNumber(reconciliation.data?.total ?? 0)} matches</div>
            </div>
            <div className="flex flex-wrap items-center gap-3 text-[11px] text-subtle">
              {(summary.data?.by_strategy ?? []).map((item: any) => (
                <span key={item.match_strategy ?? 'none'} className="flex items-center gap-1.5">
                  <Badge tone="neutral">{titleCase(item.match_strategy ?? 'none')}</Badge>
                  <span className="tabular-nums">{item.count}</span>
                </span>
              ))}
            </div>
          </div>

          {reconciliation.isError ? (
            <div className="p-4">
              <ErrorState message={(reconciliation.error as Error)?.message} onRetry={() => reconciliation.refetch()} />
            </div>
          ) : reconciliation.isLoading && !reconciliation.data ? (
            <div className="p-4">
              <LoadingState label="Loading reconciliation…" rows={6} />
            </div>
          ) : (
            <>
              <DataTable
                rows={filtered}
                rowKey={(row: any) => String(row.match_id)}
                loading={reconciliation.isFetching}
                emptyMessage="No reconciliation results for these filters"
                columns={[
                  {
                    key: 'sku',
                    header: 'Catalog SKU',
                    render: (row: any) => (
                      <span className="block max-w-[16rem]">
                        <span className="block truncate font-mono text-xs">{row.catalog_sku}</span>
                        <span className="block truncate text-[11px] text-subtle">{row.catalog_name}</span>
                      </span>
                    ),
                  },
                  {
                    key: 'scraped',
                    header: 'Scraped product',
                    render: (row: any) =>
                      row.product_id ? (
                        <Link to={`/products/${row.product_id}`} className="block max-w-[18rem] truncate text-sm">
                          {row.scraped_name}
                          {row.scraped_brand ? <span className="block truncate text-[11px] text-subtle">{row.scraped_brand}</span> : null}
                        </Link>
                      ) : (
                        <span className="text-subtle">no match</span>
                      ),
                  },
                  { key: 'catalog_price', header: 'Our price', align: 'right', render: (row: any) => formatPrice(row.catalog_price) },
                  { key: 'market_price', header: 'Market', align: 'right', hideBelow: 'sm', render: (row: any) => formatPrice(row.scraped_price_usd) },
                  {
                    key: 'gap',
                    header: 'Gap',
                    align: 'right',
                    render: (row: any) => (
                      <span className="flex items-center justify-end gap-2">
                        {row.price_gap_abs !== null && row.price_gap_abs !== undefined ? (
                          <span className="text-xs tabular-nums text-muted">{Number(row.price_gap_abs) > 0 ? '+' : ''}{Number(row.price_gap_abs).toFixed(2)}</span>
                        ) : null}
                        <DeltaPill value={row.price_gap_pct} />
                      </span>
                    ),
                  },
                  {
                    key: 'status',
                    header: 'Status',
                    align: 'center',
                    render: (row: any) => (
                      <div className="flex flex-col items-center gap-1">
                        <Badge tone={statusTone(row.match_status)}>{titleCase(row.match_status ?? 'unknown')}</Badge>
                        {row.is_price_mismatch ? <Badge tone="warning">price gap</Badge> : null}
                      </div>
                    ),
                  },
                  {
                    key: 'quality',
                    header: 'Match quality',
                    hideBelow: 'lg',
                    render: (row: any) => (
                      <span className="flex items-center gap-1.5 text-[11px]">
                        <Badge tone={row.category_match ? 'success' : 'neutral'}>{row.category_match ? 'cat ok' : 'cat?'}</Badge>
                        <Badge tone={row.brand_match ? 'success' : 'neutral'}>{row.brand_match ? 'brand ok' : 'brand?'}</Badge>
                      </span>
                    ),
                  },
                  { key: 'similarity', header: 'Sim.', align: 'right', hideBelow: 'xl', render: (row: any) => (row.similarity_score !== null ? Number(row.similarity_score).toFixed(3) : '—') },
                  { key: 'matched', header: 'Matched', align: 'right', hideBelow: 'md', render: (row: any) => formatDateTime(row.matched_at) },
                ]}
              />
              <div className="p-3">
                <Pagination page={page} pageSize={pageSize} total={reconciliation.data?.total ?? 0} onPage={setPage} onPageSize={setPageSize} />
              </div>
            </>
          )}
        </Card>
      ) : null}

      {tab === 'opportunities' ? (
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
          <Card className="xl:col-span-2" padded={false}>
            <div className="p-4 sm:p-5">
              <CardHeader
                title="Where we are dearer / cheaper"
                subtitle="Price gap versus the scraped market price, largest first"
                icon={<TrendingUp className="h-4 w-4" />}
                action={
                  <Select value={direction} onChange={(event) => setDirection(event.target.value)} aria-label="Direction" className="h-8 w-40 py-0 text-xs">
                    <option value="">Both directions</option>
                    <option value="we_are_dearer">We are dearer</option>
                    <option value="we_are_cheaper">We are cheaper</option>
                  </Select>
                }
              />
            </div>
            <DataTable
              rows={direction ? opportunityRows.filter((row: any) => row.position === direction) : opportunityRows}
              rowKey={(row: any) => row.catalog_sku}
              loading={opportunities.isFetching}
              emptyMessage="No pricing opportunities above the 1% threshold"
              columns={[
                {
                  key: 'sku',
                  header: 'SKU',
                  render: (row: any) => (
                    <span className="block max-w-[16rem]">
                      <span className="block truncate font-mono text-xs">{row.catalog_sku}</span>
                      <span className="block truncate text-[11px] text-subtle">{row.catalog_name}</span>
                    </span>
                  ),
                },
                { key: 'supplier', header: 'Supplier', hideBelow: 'md', render: (row: any) => <Badge tone="neutral">{row.supplier ?? '—'}</Badge> },
                { key: 'ours', header: 'Our price', align: 'right', render: (row: any) => formatPrice(row.catalog_price) },
                { key: 'market', header: 'Market', align: 'right', render: (row: any) => formatPrice(row.scraped_price_usd) },
                {
                  key: 'position',
                  header: 'Position',
                  align: 'center',
                  render: (row: any) => (
                    <Badge tone={row.position === 'we_are_dearer' ? 'danger' : 'success'}>
                      {row.position === 'we_are_dearer' ? 'we are dearer' : 'we are cheaper'}
                    </Badge>
                  ),
                },
                { key: 'gap', header: 'Gap', align: 'right', render: (row: any) => <DeltaPill value={row.price_gap_pct} /> },
              ]}
            />
          </Card>

          <div className="space-y-3">
            <Card>
              <CardHeader title="Gap distribution" subtitle="Opportunities by direction" icon={<TrendingDown className="h-4 w-4" />} />
              {opportunityRows.length ? (
                <DonutChart
                  data={[
                    { name: 'We are dearer', value: opportunityRows.filter((row: any) => row.position === 'we_are_dearer').length },
                    { name: 'We are cheaper', value: opportunityRows.filter((row: any) => row.position === 'we_are_cheaper').length },
                  ]}
                  height={220}
                  centerLabel="opportunities"
                />
              ) : (
                <EmptyState kind="price" title="No opportunities" />
              )}
            </Card>

            <Card>
              <CardHeader title="By supplier" subtitle="Average gap per supplier" icon={<Building2 className="h-4 w-4" />} />
              {(summary.data?.by_supplier ?? []).length ? (
                <BarSeries
                  data={(summary.data?.by_supplier ?? []).slice(0, 8).map((row: any) => ({ name: row.supplier ?? 'unknown', gap: Number(row.avg_gap_pct ?? 0) }))}
                  xKey="name"
                  bars={[{ key: 'gap', label: 'Average gap %' }]}
                  horizontal
                  height={220}
                  formatY="percent"
                />
              ) : (
                <EmptyState kind="products" title="No supplier data" />
              )}
            </Card>

            <Card>
              <CardHeader title="Match quality" subtitle={`Average similarity ${Number(totals.avg_similarity ?? 0).toFixed(3)}`} icon={<GitCompare className="h-4 w-4" />} />
              <ProgressBar value={matchRate} tone={matchRate >= 60 ? 'success' : matchRate >= 30 ? 'warning' : 'danger'} />
              <p className="mt-2 text-xs text-muted">
                {formatNumber(totals.matched ?? 0)} of {formatNumber(totals.total ?? 0)} internal SKUs matched a scraped
                product. Matching uses a three-stage cascade: SKU identifier, exact normalised name, then fuzzy similarity.
              </p>
            </Card>
          </div>
        </div>
      ) : null}

      {tab === 'skus' ? (
        <Card padded={false}>
          <div className="p-4 sm:p-5">
            <CardHeader
              title="Internal catalog"
              subtitle="The retailer's own product master that scraped data is compared against"
              icon={<Building2 className="h-4 w-4" />}
              action={
                <Button size="sm" variant="ghost" icon={<RefreshCw className="h-4 w-4" />} onClick={() => catalogProducts.refetch()}>
                  Refresh
                </Button>
              }
            />
          </div>
          <DataTable
            rows={catalogProducts.data?.items ?? []}
            rowKey={(row: any) => row.sku}
            loading={catalogProducts.isFetching}
            emptyMessage="No internal catalog rows"
            columns={[
              { key: 'sku', header: 'SKU', render: (row: any) => <span className="font-mono text-xs">{row.sku}</span> },
              { key: 'name', header: 'Name', render: (row: any) => <span className="block max-w-[22rem] truncate">{row.name}</span> },
              { key: 'brand', header: 'Brand', hideBelow: 'sm', render: (row: any) => row.brand ?? '—' },
              { key: 'category', header: 'Category', hideBelow: 'md', render: (row: any) => <Badge tone="neutral">{row.category ?? '—'}</Badge> },
              { key: 'supplier', header: 'Supplier', hideBelow: 'lg', render: (row: any) => row.supplier ?? '—' },
              { key: 'cost', header: 'Cost', align: 'right', hideBelow: 'xl', render: (row: any) => formatPrice(row.cost_price, row.currency ?? 'USD') },
              { key: 'list', header: 'List price', align: 'right', render: (row: any) => formatPrice(row.list_price, row.currency ?? 'USD') },
              { key: 'qty', header: 'Qty', align: 'right', hideBelow: 'md', render: (row: any) => formatCompact(row.qty_on_hand ?? 0) },
              {
                key: 'status',
                header: 'Status',
                align: 'center',
                render: (row: any) => <Badge tone={row.status === 'active' ? 'success' : 'neutral'}>{titleCase(row.status)}</Badge>,
              },
            ]}
          />
        </Card>
      ) : null}

      <p className="text-[11px] text-subtle">
        Reconciliation is a pipeline stage: it runs after the load, compares every active catalog SKU with the newest
        snapshot of each canonical product and stores the price gap in <code className="rounded bg-surface-3 px-1">fact_catalog_snapshot</code>.
      </p>

      {trigger.isPending ? (
        <Modal open onClose={() => undefined} title="Running the pipeline" description="Extraction, cleaning, dedupe, load, quality and reconciliation." size="sm">
          <p className="text-sm text-muted">
            This runs synchronously and usually takes a few seconds. Results refresh automatically when it completes.
          </p>
        </Modal>
      ) : null}
    </div>
  )
}