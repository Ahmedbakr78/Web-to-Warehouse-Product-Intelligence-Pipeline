import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowDown, ArrowUp, Bookmark, Braces, Check, CheckCheck, Copy, Download, ExternalLink, Filter, Layers, Link2, Minus, Pin, PinOff, Play, RotateCcw, Save, Sparkles, Wand2, X } from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import {
  Badge,
  Button,
  Card,
  CardHeader,
  ChipGroup,
  DataTable,
  DeltaPill,
  EmptyState,
  ErrorState,
  LoadingState,
  Modal,
  SearchInput,
  Segmented,
  Select,
  StatTile,
  TextInput,
  Toggle,
  useToast,
  type Column,
} from '@/components/ui'
import { endpoints } from '@/lib/api'
import { useApiQuery } from '@/hooks/useApi'
import { useDebounce } from '@/hooks/useDebounce'
import AggregateBuilder from './AggregateBuilder'
import { downloadCsv, downloadJson, toCsv, formatAvailability, formatNumber, formatPrice, formatRelative, titleCase } from '@/lib/format'

type Entity = 'products' | 'price-changes' | 'runs' | 'quality' | 'catalog' | 'new' | 'removed' | 'movers' | 'sources' | 'categories' | 'brands' | 'availability'

interface BuilderState {
  entity: Entity
  search: string
  category: string
  brand: string
  source: string
  availability: string
  inStock: '' | 'true' | 'false'
  minPrice: string
  maxPrice: string
  minRating: string
  minChangePct: string
  maxChangePct: string
  newSinceDays: string
  significantOnly: boolean
  activeOnly: boolean
  sortBy: string
  sortDir: 'asc' | 'desc'
  /** Extra sort levels (level 1 is sortBy/sortDir); honoured by multi-sort entities. */
  multiSort: { by: string; dir: 'asc' | 'desc' }[]
  pageSize: number
  columns: string[]
  /** Column keys frozen to the left edge of the preview table. */
  pinned: string[]
}

const DEFAULT_STATE: BuilderState = {
  entity: 'products',
  search: '',
  category: '',
  brand: '',
  source: '',
  availability: '',
  inStock: '',
  minPrice: '',
  maxPrice: '',
  minRating: '',
  minChangePct: '',
  maxChangePct: '',
  newSinceDays: '',
  significantOnly: false,
  activeOnly: true,
  sortBy: 'last_seen_at',
  sortDir: 'desc',
  multiSort: [],
  pageSize: 25,
  columns: ['name', 'category', 'brand', 'price', 'change', 'availability', 'last_seen'],
  pinned: ['name'],
}

const ENTITY_COLUMNS: Record<Entity, { key: string; label: string }[]> = {
  products: [
    { key: 'name', label: 'Product' },
    { key: 'category', label: 'Category' },
    { key: 'brand', label: 'Brand' },
    { key: 'price', label: 'Price' },
    { key: 'change', label: 'Price change' },
    { key: 'rating', label: 'Rating' },
    { key: 'availability', label: 'Availability' },
    { key: 'source', label: 'Source' },
    { key: 'last_seen', label: 'Last seen' },
  ],
  'price-changes': [
    { key: 'product', label: 'Product' },
    { key: 'from', label: 'Previous price' },
    { key: 'to', label: 'New price' },
    { key: 'change', label: 'Change %' },
    { key: 'direction', label: 'Direction' },
    { key: 'band', label: 'Magnitude band' },
    { key: 'date', label: 'Detected' },
  ],
  runs: [
    { key: 'run_id', label: 'Run' },
    { key: 'status', label: 'Status' },
    { key: 'trigger', label: 'Trigger' },
    { key: 'duration', label: 'Duration' },
    { key: 'extracted', label: 'Extracted' },
    { key: 'loaded', label: 'Loaded' },
    { key: 'dq', label: 'DQ score' },
  ],
  quality: [
    { key: 'code', label: 'Rule' },
    { key: 'name', label: 'Rule name' },
    { key: 'dimension', label: 'Dimension' },
    { key: 'severity', label: 'Severity' },
    { key: 'status', label: 'Status' },
    { key: 'checked', label: 'Records checked' },
  ],
  catalog: [
    { key: 'sku', label: 'Catalog SKU' },
    { key: 'name', label: 'Catalog name' },
    { key: 'scraped', label: 'Scraped product' },
    { key: 'catalog_price', label: 'Our price' },
    { key: 'market_price', label: 'Market price' },
    { key: 'gap', label: 'Gap %' },
    { key: 'status', label: 'Match status' },
  ],
  new: [
    { key: 'product', label: 'Product' },
    { key: 'category', label: 'Category' },
    { key: 'brand', label: 'Brand' },
    { key: 'price', label: 'First price' },
    { key: 'source', label: 'Source' },
    { key: 'first_seen', label: 'First seen' },
  ],
  removed: [
    { key: 'product', label: 'Product' },
    { key: 'category', label: 'Category' },
    { key: 'source', label: 'Source' },
    { key: 'last_price', label: 'Last price' },
    { key: 'missing_days', label: 'Missing days' },
  ],
  movers: [
    { key: 'product', label: 'Product' },
    { key: 'from', label: 'Previous price' },
    { key: 'to', label: 'New price' },
    { key: 'change', label: 'Change %' },
    { key: 'direction', label: 'Direction' },
    { key: 'band', label: 'Magnitude band' },
  ],
  sources: [
    { key: 'source', label: 'Source' },
    { key: 'kind', label: 'Kind' },
    { key: 'products', label: 'Products' },
    { key: 'observations', label: 'Observations' },
    { key: 'success', label: 'Success %' },
  ],
  categories: [
    { key: 'category', label: 'Category' },
    { key: 'observations', label: 'Observations' },
    { key: 'avg_price', label: 'Avg price' },
    { key: 'rating', label: 'Avg rating' },
    { key: 'new_products', label: 'New' },
    { key: 'price_changes', label: 'Changes' },
  ],
  brands: [
    { key: 'brand', label: 'Brand' },
    { key: 'category', label: 'Category' },
    { key: 'products', label: 'Products' },
    { key: 'avg_price', label: 'Avg price' },
    { key: 'rating', label: 'Avg rating' },
    { key: 'last_seen', label: 'Last seen' },
  ],
  availability: [
    { key: 'category', label: 'Category' },
    { key: 'observations', label: 'Observations' },
    { key: 'in_stock', label: 'In-stock %' },
    { key: 'out_of_stock', label: 'Out of stock' },
  ],
}

const ENTITY_HINTS: Record<Entity, string> = {
  products: 'Filter the deduplicated product catalogue with facets, price windows and change thresholds.',
  'price-changes': 'Follow price movement with direction, significance and window controls.',
  runs: 'Review pipeline execution history by status and duration.',
  quality: 'Inspect data-quality evaluations by dimension and outcome.',
  catalog: 'Compare the internal catalog against scraped market prices.',
  new: 'First-sighting events with source attribution — use New Since (days) to set the window.',
  removed: 'Absent-from-source detection with grace window and last known price.',
  movers: 'Largest absolute and relative movements, banded flash_sale to minor.',
  sources: 'Coverage matrix: products, observations and success rate per permitted source.',
  categories: 'Category leaderboard: observations, average price and rating per category.',
  brands: 'Brand leaderboard: product counts, average price and rating per brand.',
  availability: 'In-stock ratio per category with out-of-stock counts.',
}

const SORT_OPTIONS = [
  { value: 'last_seen_at', label: 'Last seen' },
  { value: 'first_seen_at', label: 'First seen' },
  { value: 'canonical_name', label: 'Name' },
  { value: 'price', label: 'Price' },
  { value: 'price_change_pct', label: 'Change %' },
  { value: 'rating', label: 'Rating' },
  { value: 'observation_count', label: 'Observations' },
]

/** Entities whose endpoints accept comma-separated multi-level sort. */
const MULTI_SORT_ENTITIES: Entity[] = ['products', 'price-changes']

const MAX_EXTRA_SORTS = 2

export default function Builder() {
  const [mode, setMode] = useState<'filters' | 'aggregate'>('filters')
  const [state, setState] = useState<BuilderState>(DEFAULT_STATE)
  const [showSave, setShowSave] = useState(false)
  const [viewName, setViewName] = useState('')
  const [viewDescription, setViewDescription] = useState('')
  const [shared, setShared] = useState(false)
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const queryClient = useQueryClient()
  const toast = useToast()
  const debouncedSearch = useDebounce(state.search, 320)

  // Restore priority: a shared `?view=` link wins, then the last working
  // state from this browser, then defaults. The param is consumed once so a
  // plain reload afterwards keeps working on the restored state.
  useEffect(() => {
    const shared = searchParams.get('view')
    if (shared) {
      const restored = decodeShareState(shared)
      if (restored) {
        setState(restored)
        toast.info('Shared view loaded', 'Filters, sort, columns and pins came from the link.')
      } else {
        toast.error('Could not open the shared view', 'The link is malformed or from another app version.')
      }
      searchParams.delete('view')
      setSearchParams(searchParams, { replace: true })
      return
    }
    const stored = localStorage.getItem('pip.builder')
    if (stored) {
      try {
        const parsed = sanitizeBuilderState(JSON.parse(stored))
        if (parsed) setState(parsed)
      } catch {
        /* ignore malformed state */
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    localStorage.setItem('pip.builder', JSON.stringify(state))
  }, [state])

  const facets = useApiQuery(['facets'], endpoints.facets, { staleTime: 300_000 })
  const savedViews = useApiQuery(['saved-views'], () => endpoints.savedViews(), { staleTime: 300_000 })

  const productParams = useMemo(() => {
    const levels = [{ by: state.sortBy, dir: state.sortDir }, ...state.multiSort]
    const multi = MULTI_SORT_ENTITIES.includes(state.entity)
    const sort_by = (multi ? levels : levels.slice(0, 1)).map((level) => level.by).join(',')
    const sort_dir = (multi ? levels : levels.slice(0, 1)).map((level) => level.dir).join(',')
    return {
      page: 1,
      page_size: state.pageSize,
      sort_by,
      sort_dir,
      q: debouncedSearch || undefined,
      category: state.category || undefined,
      brand: state.brand || undefined,
      source: state.source || undefined,
      availability: state.availability || undefined,
      in_stock: state.inStock || undefined,
      min_price: state.minPrice || undefined,
      max_price: state.maxPrice || undefined,
      min_rating: state.minRating || undefined,
      min_change_pct: state.minChangePct || undefined,
      max_change_pct: state.maxChangePct || undefined,
      new_since_days: state.newSinceDays || undefined,
      is_active: state.activeOnly || undefined,
    }
  }, [state, debouncedSearch])

  const preview = useApiQuery(
    ['builder-preview', state.entity, productParams],
    async () => {
      if (state.entity === 'products') return endpoints.products(productParams)
      if (state.entity === 'price-changes') return endpoints.priceChanges(productParams)
      if (state.entity === 'runs') return endpoints.runs({ page: 1, page_size: state.pageSize, sort_by: state.sortBy, sort_dir: state.sortDir })
      if (state.entity === 'quality') return endpoints.qualityResults({ page: 1, page_size: state.pageSize, dimension: state.category || undefined, status: state.availability || undefined })
      if (state.entity === 'new') return endpoints.products({ ...productParams, new_since_days: state.newSinceDays || '30' })
      if (state.entity === 'removed') return endpoints.removedProducts(180, state.pageSize)
      if (state.entity === 'movers') return endpoints.topMovers(state.pageSize)
      if (state.entity === 'sources') return endpoints.sourceCoverage()
      if (state.entity === 'categories') return endpoints.categories(state.pageSize)
      if (state.entity === 'brands') return endpoints.brands(state.pageSize)
      if (state.entity === 'availability') return endpoints.availability()
      return endpoints.catalogReconciliation({ page: 1, page_size: state.pageSize, match_status: state.availability || undefined, only_mismatches: state.significantOnly })
    },
    { enabled: true, placeholderData: (previous: unknown) => previous },
  )

  const saveView = useMutation({
    mutationFn: () =>
      endpoints.createSavedView({
        name: viewName,
        entity: state.entity === 'price-changes' ? 'changes' : state.entity,
        description: viewDescription || ENTITY_HINTS[state.entity],
        filters: serialiseFilters(state),
        sort_by: state.sortBy,
        sort_dir: state.sortDir,
        visible_columns: state.columns,
        is_shared: shared,
        is_favorite: true,
      }),
    onSuccess: () => {
      toast.success('View saved', `“${viewName}” is available on the ${titleCase(state.entity)} screen.`)
      setShowSave(false)
      setViewName('')
      setViewDescription('')
      void queryClient.invalidateQueries({ queryKey: ['saved-views'] })
    },
    onError: (error: Error) => toast.error('Could not save the view', error.message),
  })

  const activeFilters = countActiveFilters(state)
  // Some entities return a bare array (analytics, movers, sources) while the
  // paged ones return {items, total}: normalise so previews never render empty.
  const rows = Array.isArray(preview.data) ? preview.data : ((preview.data as any)?.items ?? [])
  const columns = ENTITY_COLUMNS[state.entity]

  function patch(changes: Partial<BuilderState>) {
    setState((current) => ({ ...current, ...changes }))
  }

  function toggleColumn(key: string) {
    setState((current) => ({
      ...current,
      columns: current.columns.includes(key) ? current.columns.filter((item) => item !== key) : [...current.columns, key],
    }))
  }

  /** Move a visible column up or down in the render order. */
  function moveColumn(key: string, direction: -1 | 1) {
    setState((current) => {
      const visible = current.columns.filter((item) => columns.some((column) => column.key === item))
      const hidden = columns.map((column) => column.key).filter((item) => !visible.includes(item))
      const index = visible.indexOf(key)
      const target = index + direction
      if (index === -1 || target < 0 || target >= visible.length) return current
      const next = [...visible]
      const [moved] = next.splice(index, 1)
      next.splice(target, 0, moved)
      return { ...current, columns: [...next, ...hidden] }
    })
  }

  /** Freeze or release a column at the left edge of the preview table. */
  function togglePin(key: string) {
    setState((current) => ({
      ...current,
      pinned: current.pinned.includes(key) ? current.pinned.filter((item) => item !== key) : [...current.pinned, key],
    }))
  }

  /** Duplicate a saved view under a new name instead of starting from blank. */
  function cloneView(view: any) {
    applySavedView(view)
    setViewName(`${view.name} (copy)`)
    setViewDescription(view.description ?? '')
    setShared(Boolean(view.is_shared))
    setShowSave(true)
  }

  /** Share the whole composition — filters, sort levels, columns and pins. */
  function copyShareLink() {
    const payload = {
      v: 1,
      entity: state.entity,
      filters: serialiseFilters(state),
      sort_by: state.sortBy,
      sort_dir: state.sortDir,
      multi_sort: state.multiSort,
      columns: state.columns,
      pinned: state.pinned,
    }
    const encoded = btoa(unescape(encodeURIComponent(JSON.stringify(payload))))
      .replaceAll('+', '-')
      .replaceAll('/', '_')
      .replace(/=+$/, '')
    const url = `${window.location.origin}/builder?view=${encoded}`
    navigator.clipboard?.writeText(url).then(
      () => toast.success('Share link copied', 'Anyone with access opens this exact composition.'),
      () => toast.error('Clipboard unavailable', url),
    )
  }

  /** Append another sort level (up to 3 total, level 1 is the Sort control). */
  function addSortLevel() {
    if (state.multiSort.length >= MAX_EXTRA_SORTS) return
    const used = new Set([state.sortBy, ...state.multiSort.map((level) => level.by)])
    const fallback = SORT_OPTIONS.find((option) => !used.has(option.value)) ?? SORT_OPTIONS[0]
    patch({ multiSort: [...state.multiSort, { by: fallback.value, dir: 'desc' as const }] })
  }

  function patchSortLevel(index: number, changes: Partial<{ by: string; dir: 'asc' | 'desc' }>) {
    patch({ multiSort: state.multiSort.map((level, position) => (position === index ? { ...level, ...changes } : level)) })
  }

  function removeSortLevel(index: number) {
    patch({ multiSort: state.multiSort.filter((_, position) => position !== index) })
  }

  /** Share the composed query as a ready-to-run REST call. */
  function copyCurlRequest() {
    const paths: Record<Entity, string> = {
      products: '/products',
      'price-changes': '/changes/price',
      runs: '/pipeline/runs',
      quality: '/quality/results',
      catalog: '/catalog/reconciliation',
      new: '/changes/new',
      removed: '/changes/removed',
      movers: '/changes/top-movers',
      sources: '/analytics/sources',
      categories: '/analytics/categories',
      brands: '/analytics/brands',
      availability: '/analytics/availability',
    }
    const params = new URLSearchParams(cleanParams(productParams))
    const base = `${window.location.origin}${import.meta.env.VITE_API_BASE_URL ?? '/api/v1'}${paths[state.entity]}?${params.toString()}`
    const cmd = `curl -s "${base}" -H "Authorization: Bearer $TOKEN"`
    navigator.clipboard?.writeText(cmd).then(
      () => toast.success('cURL copied', 'Paste it in any terminal with $TOKEN set.'),
      () => toast.error('Clipboard unavailable', cmd),
    )
  }

  /** Share the composed query as a ready-to-run REST call. */
  function copyApiRequest() {
    const paths: Record<Entity, string> = {
      products: '/products',
      'price-changes': '/changes/price',
      runs: '/pipeline/runs',
      quality: '/quality/results',
      catalog: '/catalog/reconciliation',
      new: '/changes/new',
      removed: '/changes/removed',
      movers: '/changes/top-movers',
      sources: '/analytics/sources',
      categories: '/analytics/categories',
      brands: '/analytics/brands',
      availability: '/analytics/availability',
    }
    const params = new URLSearchParams(cleanParams(productParams))
    const url = `${window.location.origin}${import.meta.env.VITE_API_BASE_URL ?? '/api/v1'}${paths[state.entity]}?${params.toString()}`
    navigator.clipboard?.writeText(url).then(
      () => toast.success('API request copied', 'Send it with `Authorization: Bearer <token>`.'),
      () => toast.error('Clipboard unavailable', url),
    )
  }

  /** Current rows, flattening each visible column back to its plain-text value. */
  function exportPreview(format: 'csv' | 'json') {
    const visibleColumns = columns.filter((column) => state.columns.includes(column.key))
    const header = visibleColumns.map((column) => column.label)
    const body = rows.map((row: any) => visibleColumns.map((column) => plainCell(state.entity, column.key, row)))
    if (format === 'csv') downloadCsv(`builder-${state.entity}.csv`, toCsv(header, body))
    else downloadJson(`builder-${state.entity}.json`, { entity: state.entity, filters: serialiseFilters(state), rows })
  }

  function applySavedView(view: any) {
    const filters = view.filters ?? {}
    const restored = sanitizeBuilderState({
      ...filters,
      entity: view.entity === 'changes' ? 'price-changes' : view.entity,
      sort_by: view.sort_by,
      sort_dir: view.sort_dir,
      columns: view.visible_columns,
    })
    setState(restored ?? { ...DEFAULT_STATE, columns: DEFAULT_STATE.columns })
    toast.info('View applied', view.name)
  }

  return (
    <div className="space-y-4">
      {/* ------------------------------------------------------- mode switch */}
      <div className="flex items-center justify-between gap-3">
        <Segmented
          options={[
            { id: 'filters', label: 'Filter & customise' },
            { id: 'aggregate', label: 'Group & aggregate' },
          ]}
          value={mode}
          onChange={(value) => setMode(value as 'filters' | 'aggregate')}
        />
        {mode === 'aggregate' ? (
          <span className="flex items-center gap-1.5 text-[11px] text-subtle">
            <Layers className="h-3.5 w-3.5" aria-hidden />
            Server-side aggregation via <code className="rounded bg-surface-3 px-1 font-mono">/builder/query</code>
          </span>
        ) : null}
      </div>

      {mode === 'aggregate' ? (
        <AggregateBuilder />
      ) : (
        <>
      {/* ------------------------------------------------------------- header */}
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <CardHeader
              title="Compose a custom view"
              subtitle="Filters, sort order and columns are evaluated live against the warehouse"
              icon={<Wand2 className="h-4 w-4" />}
            />
            <p className="-mt-2 max-w-2xl text-xs text-muted">{ENTITY_HINTS[state.entity]}</p>
          </div>
          <div className="flex shrink-0 gap-2">
            <Button size="sm" variant="secondary" icon={<RotateCcw className="h-4 w-4" />} onClick={() => setState(DEFAULT_STATE)}>
              Reset
            </Button>
            <Button size="sm" variant="primary" icon={<Save className="h-4 w-4" />} onClick={() => setShowSave(true)} disabled={!viewName && activeFilters === 0}>
              Save view
            </Button>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <ChipGroup
            options={(Object.keys(ENTITY_COLUMNS) as Entity[]).map((entity) => ({ id: entity, label: titleCase(entity) }))}
            value={state.entity}
            onChange={(entity) => patch({ entity: entity as Entity })}
          />
          <span className="ml-auto flex items-center gap-2 text-xs text-subtle">
            <Filter className="h-3.5 w-3.5" aria-hidden />
            {activeFilters} active {activeFilters === 1 ? 'filter' : 'filters'}
          </span>
        </div>
      </Card>

      {/* ------------------------------------------------------------- controls */}
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-4">
        <Card className="xl:col-span-3">
          <CardHeader title="Filters" subtitle="Applied instantly to the preview" icon={<Filter className="h-4 w-4" />} />
          <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
            <div className="lg:col-span-2">
              <p className="stat-label mb-1.5">Search</p>
              <SearchInput value={state.search} onChange={(value) => patch({ search: value })} placeholder="Name, brand, SKU…" />
            </div>
            <div>
              <p className="stat-label mb-1.5">Category</p>
              <Select value={state.category} onChange={(event) => patch({ category: event.target.value })}>
                <option value="">Any</option>
                {(facets.data?.categories ?? []).map((item: any) => (
                  <option key={item.category_name} value={item.category_name}>
                    {item.category_name} ({item.count})
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <p className="stat-label mb-1.5">Brand</p>
              <Select value={state.brand} onChange={(event) => patch({ brand: event.target.value })}>
                <option value="">Any</option>
                {(facets.data?.brands ?? []).slice(0, 60).map((item: any) => (
                  <option key={item.brand} value={item.brand}>
                    {item.brand} ({item.count})
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <p className="stat-label mb-1.5">Source</p>
              <Select value={state.source} onChange={(event) => patch({ source: event.target.value })}>
                <option value="">Any</option>
                {(facets.data?.sources ?? []).map((item: any) => (
                  <option key={item.source_code} value={item.source_code}>
                    {item.source_code} ({item.count})
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <p className="stat-label mb-1.5">Availability</p>
              <Select value={state.availability} onChange={(event) => patch({ availability: event.target.value })}>
                <option value="">Any</option>
                {(facets.data?.availability ?? []).map((item: any) => (
                  <option key={item.availability} value={item.availability}>
                    {formatAvailability(item.availability).label} ({item.count})
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <p className="stat-label mb-1.5">Price range (USD)</p>
              <div className="flex items-center gap-1">
                <TextInput placeholder="min" value={state.minPrice} onChange={(event) => patch({ minPrice: event.target.value })} inputMode="decimal" />
                <TextInput placeholder="max" value={state.maxPrice} onChange={(event) => patch({ maxPrice: event.target.value })} inputMode="decimal" />
              </div>
            </div>
            <div>
              <p className="stat-label mb-1.5">Min rating</p>
              <Select value={state.minRating} onChange={(event) => patch({ minRating: event.target.value })}>
                <option value="">Any</option>
                <option value="3">3+</option>
                <option value="4">4+</option>
                <option value="4.5">4.5+</option>
              </Select>
            </div>
            <div>
              <p className="stat-label mb-1.5">Price change % (drop / rise)</p>
              <div className="flex items-center gap-1">
                <TextInput placeholder="≤" value={state.minChangePct} onChange={(event) => patch({ minChangePct: event.target.value })} inputMode="decimal" />
                <TextInput placeholder="≥" value={state.maxChangePct} onChange={(event) => patch({ maxChangePct: event.target.value })} inputMode="decimal" />
              </div>
            </div>
            <div>
              <p className="stat-label mb-1.5">New within (days)</p>
              <TextInput placeholder="e.g. 7" value={state.newSinceDays} onChange={(event) => patch({ newSinceDays: event.target.value })} inputMode="numeric" />
            </div>
            <div className="sm:col-span-2">
              <p className="stat-label mb-1.5">
                Sort levels
                {!MULTI_SORT_ENTITIES.includes(state.entity) && state.multiSort.length ? (
                  <span className="ml-1 font-normal normal-case text-subtle">— level 1 only for {titleCase(state.entity)}</span>
                ) : null}
              </p>
              <div className="space-y-1.5">
                <div className="flex items-center gap-1">
                  <span className="w-4 shrink-0 text-center font-mono text-[11px] text-subtle">1</span>
                  <Select value={state.sortBy} onChange={(event) => patch({ sortBy: event.target.value })} className="flex-1">
                    {SORT_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </Select>
                  <Select value={state.sortDir} onChange={(event) => patch({ sortDir: event.target.value as 'asc' | 'desc' })} className="w-20">
                    <option value="desc">Desc</option>
                    <option value="asc">Asc</option>
                  </Select>
                </div>
                {state.multiSort.map((level, index) => (
                  <div key={`${level.by}-${index}`} className="flex items-center gap-1">
                    <span className="w-4 shrink-0 text-center font-mono text-[11px] text-subtle">{index + 2}</span>
                    <Select value={level.by} onChange={(event) => patchSortLevel(index, { by: event.target.value })} className="flex-1">
                      {SORT_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </Select>
                    <Select value={level.dir} onChange={(event) => patchSortLevel(index, { dir: event.target.value as 'asc' | 'desc' })} className="w-20">
                      <option value="desc">Desc</option>
                      <option value="asc">Asc</option>
                    </Select>
                    <button
                      onClick={() => removeSortLevel(index)}
                      aria-label={`Remove sort level ${index + 2}`}
                      className="rounded-md p-1.5 text-subtle hover:bg-surface-3 hover:text-ink"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
                {state.multiSort.length < MAX_EXTRA_SORTS ? (
                  <button onClick={addSortLevel} className="text-xs font-medium text-brand-500 hover:underline">
                    + Add tie-breaker level
                  </button>
                ) : null}
              </div>
            </div>
            <div>
              <p className="stat-label mb-1.5">Rows</p>
              <Select value={String(state.pageSize)} onChange={(event) => patch({ pageSize: Number(event.target.value) })}>
                {[10, 25, 50, 100].map((size) => (
                  <option key={size} value={String(size)}>
                    {size}
                  </option>
                ))}
              </Select>
            </div>
            <div className="flex items-end gap-4 sm:col-span-2 lg:col-span-4">
              <Toggle checked={state.activeOnly} onChange={(checked) => patch({ activeOnly: checked })} label="Active products only" />
              <Toggle checked={state.significantOnly} onChange={(checked) => patch({ significantOnly: checked })} label="Significant only" description="Price changes ≥ 2% or catalog mismatches" />
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader title="Columns" subtitle={`${state.columns.length} visible${state.pinned.length ? ` · ${state.pinned.length} pinned` : ''}`} icon={<Sparkles className="h-4 w-4" />} />
          <div className="max-h-80 space-y-1 overflow-auto pr-1">
            {columns.map((column) => {
              const visibleIndex = state.columns.indexOf(column.key)
              const canMoveUp = visibleIndex > 0
              const canMoveDown = column.key !== state.columns[state.columns.length - 1]
              const isPinned = state.pinned.includes(column.key)
              return (
                <div key={column.key} className="flex items-center gap-1 rounded-lg px-1 py-0.5 hover:bg-surface-2">
                  <div className="min-w-0 flex-1">
                    <Toggle
                      checked={state.columns.includes(column.key)}
                      onChange={() => toggleColumn(column.key)}
                      label={column.label}
                    />
                  </div>
                  <div className="flex shrink-0 gap-0.5">
                    <button
                      onClick={() => togglePin(column.key)}
                      disabled={!state.columns.includes(column.key)}
                      aria-label={isPinned ? `Unpin ${column.label}` : `Pin ${column.label} to the left edge`}
                      title={isPinned ? 'Unpin' : 'Pin to the left edge'}
                      className="rounded-md p-1 text-subtle hover:bg-surface-3 hover:text-ink disabled:opacity-30 disabled:hover:bg-transparent"
                    >
                      {isPinned ? <PinOff className="h-3.5 w-3.5 text-brand-500" /> : <Pin className="h-3.5 w-3.5" />}
                    </button>
                    <button
                      onClick={() => moveColumn(column.key, -1)}
                      disabled={!state.columns.includes(column.key) || !canMoveUp}
                      aria-label={`Move ${column.label} earlier`}
                      className="rounded-md p-1 text-subtle hover:bg-surface-3 hover:text-ink disabled:opacity-30 disabled:hover:bg-transparent"
                    >
                      <ArrowUp className="h-3.5 w-3.5" />
                    </button>
                    <button
                      onClick={() => moveColumn(column.key, 1)}
                      disabled={!state.columns.includes(column.key) || !canMoveDown}
                      aria-label={`Move ${column.label} later`}
                      className="rounded-md p-1 text-subtle hover:bg-surface-3 hover:text-ink disabled:opacity-30 disabled:hover:bg-transparent"
                    >
                      <ArrowDown className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
          <div className="mt-3 flex gap-2 border-t border-line pt-3">
            <Button size="sm" variant="ghost" icon={<CheckCheck className="h-4 w-4" />} onClick={() => patch({ columns: columns.map((column) => column.key) })}>
              All
            </Button>
            <Button size="sm" variant="ghost" icon={<Minus className="h-4 w-4" />} onClick={() => patch({ columns: columns.slice(0, 3).map((column) => column.key) })}>
              Minimal
            </Button>
          </div>
        </Card>
      </div>

      {/* ------------------------------------------------------------- saved views */}
      {savedViews.data?.length ? (
        <Card>
          <CardHeader title="Saved views" subtitle="Reusable presets you or a colleague created" icon={<Bookmark className="h-4 w-4" />} />
          <div className="flex flex-wrap gap-2">
            {savedViews.data.map((view: any) => (
              <div
                key={view.view_id}
                className="flex items-stretch overflow-hidden rounded-lg border border-line bg-surface-2 hover:border-brand-400 dark:hover:border-brand-500"
              >
                <button onClick={() => applySavedView(view)} className="px-3 py-2 text-left" title="Apply this view">
                  <p className="text-xs font-medium text-ink">
                    {view.name}
                    {view.is_favorite ? <span className="ml-1 text-warning">★</span> : null}
                  </p>
                  <p className="text-[11px] text-subtle">
                    {titleCase(view.entity)} · used {view.use_count ?? 0}× · {formatRelative(view.created_at)}
                  </p>
                </button>
                <button
                  onClick={() => cloneView(view)}
                  aria-label={`Duplicate ${view.name} under a new name`}
                  title="Duplicate under a new name"
                  className="border-l border-line px-2 text-subtle hover:bg-surface-3 hover:text-ink"
                >
                  <Copy className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        </Card>
      ) : null}

      {/* ------------------------------------------------------------- preview */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatTile label="Matching records" value={formatNumber((preview.data as any)?.total ?? rows.length)} hint={titleCase(state.entity)} />
        <StatTile label="Active filters" value={String(activeFilters)} hint="Serialised with the saved view" tone="info" />
        <StatTile
          label="Columns shown"
          value={`${state.columns.length}/${columns.length}`}
          hint="Reorder by toggling visibility"
          tone="neutral"
        />
      </div>

      <Card padded={false}>
        <div className="flex flex-wrap items-center justify-between gap-2 p-4 sm:p-5">
          <CardHeader
            title="Preview"
            subtitle={`Live query against the ${titleCase(state.entity)} endpoint`}
            icon={<Play className="h-4 w-4" />}
          />
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="ghost" icon={<Copy className="h-4 w-4" />} onClick={copyApiRequest}>
              Copy API request
            </Button>
            <Button size="sm" variant="ghost" icon={<Braces className="h-4 w-4" />} onClick={copyCurlRequest}>
              Copy cURL
            </Button>
            <Button size="sm" variant="ghost" icon={<Link2 className="h-4 w-4" />} onClick={copyShareLink}>
              Share link
            </Button>
            <Button size="sm" variant="secondary" icon={<Download className="h-4 w-4" />} onClick={() => exportPreview('csv')} disabled={!rows.length}>
              CSV
            </Button>
            <Button size="sm" variant="ghost" icon={<Braces className="h-4 w-4" />} onClick={() => exportPreview('json')} disabled={!rows.length}>
              JSON
            </Button>
            {state.entity === 'products' ? (
              <Button size="sm" variant="ghost" icon={<ExternalLink className="h-4 w-4" />} onClick={() => navigate(`/products?${new URLSearchParams(cleanParams(productParams)).toString()}`)}>
                Open as a page
              </Button>
            ) : null}
          </div>
        </div>
        {preview.isError ? (
          <div className="p-4">
            <ErrorState message={(preview.error as Error)?.message} onRetry={() => preview.refetch()} />
          </div>
        ) : preview.isLoading && !preview.data ? (
          <div className="p-4">
            <LoadingState label="Running preview query…" rows={5} />
          </div>
        ) : rows.length === 0 ? (
          <EmptyState kind="search" title="No records match" message="Relax a filter or widen the price window." />
        ) : (
          <DataTable
            rows={rows}
            rowKey={(row: any, index: number) => `${row.product_id ?? row.change_id ?? row.run_id ?? row.result_id ?? row.match_id ?? index}`}
            loading={preview.isFetching}
            columns={buildColumns(state.entity, state.columns, state.pinned)}
          />
        )}
      </Card>

      <Card>
        <CardHeader title="Cross-entity recipes" subtitle="Joins the filter mode cannot express — run in QueryLab or /builder/query" icon={<Layers className="h-4 w-4" />} />
        <div className="grid grid-cols-1 gap-2 text-xs text-muted md:grid-cols-3">
          <div className="rounded-lg bg-surface-2 p-3"><p className="font-semibold text-ink">Products × price changes</p><code className="mt-1 block break-all font-mono text-[10px]">products ⨝ price_changes ON product_id — movers with category + brand</code></div>
          <div className="rounded-lg bg-surface-2 p-3"><p className="font-semibold text-ink">Market × catalog gaps</p><code className="mt-1 block break-all font-mono text-[10px]">catalog_reconciliation WHERE price_gap_pct &gt; 10 — pricing opportunities</code></div>
          <div className="rounded-lg bg-surface-2 p-3"><p className="font-semibold text-ink">Quality × runs</p><code className="mt-1 block break-all font-mono text-[10px]">quality_latest ⨝ pipeline_runs ON run_id — DQ regression per run</code></div>
        </div>
        <p className="mt-2 text-[11px] text-subtle">Tip: switch to <span className="font-medium">Group &amp; aggregate</span> for server-side group-by, 6 aggregates, 15 operators, live SQL preview and chart. All builder SQL is whitelist-assembled with bind parameters.</p>
      </Card>

      {/* ------------------------------------------------------------- save modal */}
      <Modal
        open={showSave}
        onClose={() => setShowSave(false)}
        title="Save this view"
        description="The current filters, sort levels, columns and pins are stored and become available as a preset."
        footer={
          <>
            <Button variant="ghost" icon={<X className="h-4 w-4" />} onClick={() => setShowSave(false)}>
              Cancel
            </Button>
            <Button variant="primary" icon={<Check className="h-4 w-4" />} loading={saveView.isPending} disabled={!viewName.trim()} onClick={() => saveView.mutate()}>
              Save view
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <div>
            <p className="stat-label mb-1.5">Name</p>
            <TextInput value={viewName} onChange={(event) => setViewName(event.target.value)} placeholder="e.g. Electronics price drops" autoFocus />
          </div>
          <div>
            <p className="stat-label mb-1.5">Description (optional)</p>
            <TextInput value={viewDescription} onChange={(event) => setViewDescription(event.target.value)} placeholder="What is this view used for?" />
          </div>
          <Toggle checked={shared} onChange={setShared} label="Share with the whole team" description="Shared views appear for every account" />
          <div className="rounded-lg bg-surface-2 p-3">
            <p className="stat-label mb-1.5">Serialised filters</p>
            <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-all font-mono text-[10px] leading-relaxed text-muted">
              {JSON.stringify(serialiseFilters(state), null, 2)}
            </pre>
          </div>
        </div>
      </Modal>
        </>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ helpers */
/** Plain-text value for one builder column, mirroring how the table renders it. */
function plainCell(entity: Entity, key: string, row: any): string {
  const string = (value: unknown) => (value === undefined || value === null ? '' : String(value))
  switch (entity) {
    case 'products':
      switch (key) {
        case 'name': return string(row.canonical_name)
        case 'category': return string(row.category_name)
        case 'brand': return string(row.brand)
        case 'price': return string(row.price_usd ?? row.price)
        case 'change': return string(row.price_change_pct)
        case 'rating': return string(row.rating ?? '')
        case 'availability': return string(row.availability)
        case 'source': return string(row.source_code)
        case 'last_seen': return string(row.last_seen_at)
        default: return ''
      }
    case 'price-changes':
      switch (key) {
        case 'product': return string(row.canonical_name)
        case 'from': return string(row.previous_price)
        case 'to': return string(row.new_price)
        case 'change': return string(row.change_pct)
        case 'direction': return string(row.direction)
        case 'band': return string(row.magnitude_band)
        case 'date': return string(row.detected_at ?? row.full_date)
        default: return ''
      }
    case 'runs':
      switch (key) {
        case 'run_id': return string(row?.run_id)
        case 'status': return string(row?.status)
        case 'trigger': return string(row?.trigger)
        case 'duration': return string(row?.duration_ms)
        case 'extracted': return string(row?.records_extracted)
        case 'loaded': return string(row?.records_valid)
        case 'dq': return string(row?.dq_score)
        default: return ''
      }
    case 'quality':
      switch (key) {
        case 'code': return string(row.rule_code)
        case 'name': return string(row.rule_name)
        case 'dimension': return string(row.dimension)
        case 'severity': return string(row.severity)
        case 'status': return string(row.status)
        case 'checked': return string(row.records_checked)
        default: return ''
      }
    case 'catalog':
      switch (key) {
        case 'sku': return string(row.catalog_sku)
        case 'name': return string(row.catalog_name)
        case 'scraped': return string(row.scraped_name)
        case 'catalog_price': return string(row.catalog_price)
        case 'market_price': return string(row.scraped_price_usd)
        case 'gap': return string(row.price_gap_pct)
        case 'status': return string(row.match_status)
        default: return ''
      }
    case 'new':
      switch (key) {
        case 'product': return string(row.canonical_name)
        case 'category': return string(row.category_name)
        case 'brand': return string(row.brand)
        case 'price': return string(row.price_usd ?? row.first_seen_price_usd ?? row.price)
        case 'source': return string(row.source_code)
        case 'first_seen': return string(row.first_seen_at)
        default: return ''
      }
    case 'removed':
      switch (key) {
        case 'product': return string(row.canonical_name)
        case 'category': return string(row.category_name)
        case 'source': return string(row.source_code)
        case 'last_price': return string(row.last_known_price_usd)
        case 'missing_days': return string(row.days_missing)
        default: return ''
      }
    case 'movers':
      switch (key) {
        case 'product': return string(row.canonical_name)
        case 'from': return string(row.previous_price)
        case 'to': return string(row.new_price)
        case 'change': return string(row.change_pct)
        case 'direction': return string(row.direction)
        case 'band': return string(row.magnitude_band)
        default: return ''
      }
    case 'sources':
      switch (key) {
        case 'source': return string(row.source_code ?? row.source_name)
        case 'kind': return string(row.kind)
        case 'products': return string(row.products_seen ?? row.product_count)
        case 'observations': return string(row.observations)
        case 'success': return string(row.success_rate_pct)
        default: return ''
      }
    case 'categories':
      switch (key) {
        case 'category': return string(row.category_name)
        case 'observations': return string(row.observations)
        case 'avg_price': return string(row.avg_price)
        case 'rating': return string(row.avg_rating)
        case 'new_products': return string(row.new_products)
        case 'price_changes': return string(row.price_changes)
        default: return ''
      }
    case 'brands':
      switch (key) {
        case 'brand': return string(row.brand)
        case 'category': return string(row.category_name)
        case 'products': return string(row.product_count)
        case 'avg_price': return string(row.avg_price_usd)
        case 'rating': return string(row.avg_rating)
        case 'last_seen': return string(row.last_seen_at)
        default: return ''
      }
    case 'availability':
      switch (key) {
        case 'category': return string(row.category_name)
        case 'observations': return string(row.observations)
        case 'in_stock': return string(row.in_stock_pct)
        case 'out_of_stock': return string(row.out_of_stock_count)
        default: return ''
      }
  }
}

function countActiveFilters(state: BuilderState): number {
  return [
    state.search,
    state.category,
    state.brand,
    state.source,
    state.availability,
    state.inStock,
    state.minPrice,
    state.maxPrice,
    state.minRating,
    state.minChangePct,
    state.maxChangePct,
    state.newSinceDays,
  ].filter(Boolean).length + (state.significantOnly ? 1 : 0)
}

function serialiseFilters(state: BuilderState): Record<string, unknown> {
  const filters: Record<string, unknown> = { entity: state.entity }
  const map: Record<string, string | boolean> = {
    search: state.search,
    category: state.category,
    brand: state.brand,
    source: state.source,
    availability: state.availability,
    in_stock: state.inStock,
    min_price: state.minPrice,
    max_price: state.maxPrice,
    min_rating: state.minRating,
    min_change_pct: state.minChangePct,
    max_change_pct: state.maxChangePct,
    new_since_days: state.newSinceDays,
    significant_only: state.significantOnly,
    active_only: state.activeOnly,
  }
  Object.entries(map).forEach(([key, value]) => {
    if (value !== '' && value !== false) filters[key] = value
  })
  // Layout travels with the view so Apply / Share restore the full composition.
  if (state.pinned.length) filters.pinned_columns = [...state.pinned]
  if (state.multiSort.length) filters.multi_sort = state.multiSort.map((level) => ({ ...level }))
  return filters
}

/** Validate an unknown blob (saved view, share link, old localStorage) into a
 *  safe BuilderState, or return null when the entity itself is unusable. */
function sanitizeBuilderState(candidate: any): BuilderState | null {
  if (!candidate || typeof candidate !== 'object') return null
  const entity = candidate.entity as Entity
  if (!ENTITY_COLUMNS[entity]) return null
  const validKeys = new Set(ENTITY_COLUMNS[entity].map((column) => column.key))
  const sortValues = new Set(SORT_OPTIONS.map((option) => option.value))

  const pickColumns = (value: unknown): string[] | null => {
    if (!Array.isArray(value)) return null
    const kept = value.filter((key): key is string => typeof key === 'string' && validKeys.has(key))
    return kept.length ? kept : null
  }
  const sanitiseSort = (value: unknown): { by: string; dir: 'asc' | 'desc' }[] => {
    if (!Array.isArray(value)) return []
    return value
      .filter(
        (level): level is { by: string; dir: 'asc' | 'desc' } =>
          Boolean(level) &&
          typeof level === 'object' &&
          typeof (level as any).by === 'string' &&
          sortValues.has((level as any).by) &&
          ((level as any).dir === 'asc' || (level as any).dir === 'desc'),
      )
      .slice(0, MAX_EXTRA_SORTS)
      .map((level) => ({ by: level.by, dir: level.dir }))
  }
  const text = (value: unknown): string => (typeof value === 'string' ? value : '')
  const flag = (value: unknown): boolean => value === true

  return {
    entity,
    search: text(candidate.search),
    category: text(candidate.category),
    brand: text(candidate.brand),
    source: text(candidate.source),
    availability: text(candidate.availability),
    inStock: ['true', 'false'].includes(candidate.in_stock) ? candidate.in_stock : '',
    minPrice: text(candidate.min_price),
    maxPrice: text(candidate.max_price),
    minRating: text(candidate.min_rating),
    minChangePct: text(candidate.min_change_pct),
    maxChangePct: text(candidate.max_change_pct),
    newSinceDays: text(candidate.new_since_days),
    significantOnly: flag(candidate.significant_only),
    activeOnly: candidate.active_only === undefined ? true : flag(candidate.active_only),
    sortBy: typeof candidate.sort_by === 'string' && sortValues.has(candidate.sort_by) ? candidate.sort_by : 'last_seen_at',
    sortDir: candidate.sort_dir === 'asc' ? 'asc' : 'desc',
    multiSort: sanitiseSort(candidate.multi_sort),
    pageSize: [10, 25, 50, 100].includes(candidate.page_size) ? candidate.page_size : 25,
    columns: pickColumns(candidate.columns) ?? ENTITY_COLUMNS[entity].map((column) => column.key),
    pinned: pickColumns(candidate.pinned_columns ?? candidate.pinned) ?? [],
  }
}

/** Decode a `?view=` share link into a safe BuilderState. */
function decodeShareState(encoded: string): BuilderState | null {
  try {
    const padded = encoded.replaceAll('-', '+').replaceAll('_', '/')
    const json = decodeURIComponent(escape(atob(padded)))
    const payload = JSON.parse(json)
    if (!payload || typeof payload !== 'object' || payload.v !== 1) return null
    return sanitizeBuilderState({ ...payload.filters, ...payload })
  } catch {
    return null
  }
}

function cleanParams(params: Record<string, unknown>): Record<string, string> {
  const output: Record<string, string> = {}
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') output[key] = String(value)
  })
  return output
}

function buildColumns(entity: Entity, visible: string[], pinned: string[] = []): Column<any>[] {
  const has = (key: string) => visible.includes(key)
  const isPinned = (key: string) => pinned.includes(key)
  const all: Record<Entity, Record<string, Column<any>>> = {
    products: {
      name: {
        key: 'name',
        header: 'Product',
        render: (row: any) => <span className="block max-w-[20rem] truncate font-medium">{row.canonical_name}</span>,
      },
      category: { key: 'category', header: 'Category', hideBelow: 'sm', render: (row: any) => <Badge tone="neutral">{row.category_name ?? '—'}</Badge> },
      brand: { key: 'brand', header: 'Brand', hideBelow: 'md', render: (row: any) => row.brand ?? '—' },
      price: { key: 'price', header: 'Price', align: 'right', render: (row: any) => formatPrice(row.price_usd ?? row.price, row.currency ?? 'USD') },
      change: { key: 'change', header: 'Change', align: 'right', render: (row: any) => <DeltaPill value={row.price_change_pct} /> },
      rating: { key: 'rating', header: 'Rating', align: 'center', hideBelow: 'lg', render: (row: any) => (row.rating ? Number(row.rating).toFixed(1) : '—') },
      availability: {
        key: 'availability',
        header: 'Availability',
        render: (row: any) => {
          const info = formatAvailability(row.availability)
          return <Badge tone={info.tone === 'info' ? 'info' : info.tone}>{info.label}</Badge>
        },
      },
      source: { key: 'source', header: 'Source', hideBelow: 'xl', render: (row: any) => <Badge tone="neutral">{row.source_code ?? '—'}</Badge> },
      last_seen: { key: 'last_seen', header: 'Last seen', align: 'right', hideBelow: 'lg', render: (row: any) => formatRelative(row.last_seen_at) },
    },
    'price-changes': {
      product: { key: 'product', header: 'Product', render: (row: any) => <span className="block max-w-[20rem] truncate">{row.canonical_name}</span> },
      from: { key: 'from', header: 'From', align: 'right', render: (row: any) => formatPrice(row.previous_price) },
      to: { key: 'to', header: 'To', align: 'right', render: (row: any) => formatPrice(row.new_price) },
      change: { key: 'change', header: 'Change', align: 'right', render: (row: any) => <DeltaPill value={row.change_pct} /> },
      direction: { key: 'direction', header: 'Direction', hideBelow: 'md', render: (row: any) => <Badge tone={row.direction === 'decrease' ? 'success' : 'danger'}>{titleCase(row.direction)}</Badge> },
      band: { key: 'band', header: 'Band', hideBelow: 'lg', render: (row: any) => <Badge tone="neutral">{row.magnitude_band ?? '—'}</Badge> },
      date: { key: 'date', header: 'Detected', align: 'right', hideBelow: 'md', render: (row: any) => formatRelative(row.detected_at ?? row.full_date) },
    },
    runs: {
      run_id: { key: 'run_id', header: 'Run', render: (row: any) => <span className="font-mono text-xs">{row.run_id?.slice(0, 10)}</span> },
      status: { key: 'status', header: 'Status', render: (row: any) => <Badge tone={row.status === 'success' ? 'success' : row.status === 'partial' ? 'warning' : 'danger'}>{row.status}</Badge> },
      trigger: { key: 'trigger', header: 'Trigger', hideBelow: 'sm', render: (row: any) => <Badge tone="neutral">{titleCase(row.trigger ?? 'manual')}</Badge> },
      duration: { key: 'duration', header: 'Duration', align: 'right', hideBelow: 'md', render: (row: any) => `${Math.round((row.duration_ms ?? 0) / 100) / 10}s` },
      extracted: { key: 'extracted', header: 'Extracted', align: 'right', render: (row: any) => formatNumber(row.records_extracted ?? 0) },
      loaded: { key: 'loaded', header: 'Loaded', align: 'right', hideBelow: 'sm', render: (row: any) => formatNumber(row?.records_valid ?? 0) },
      dq: { key: 'dq', header: 'DQ', align: 'right', render: (row: any) => (row.dq_score ?? '—') },
    },
    quality: {
      code: { key: 'code', header: 'Rule', render: (row: any) => <span className="font-mono text-xs">{row.rule_code}</span> },
      name: { key: 'name', header: 'Rule name', hideBelow: 'sm', render: (row: any) => row.rule_name },
      dimension: { key: 'dimension', header: 'Dimension', hideBelow: 'md', render: (row: any) => <Badge tone="neutral">{row.dimension}</Badge> },
      severity: { key: 'severity', header: 'Severity', hideBelow: 'lg', render: (row: any) => <Badge tone={row.severity === 'critical' ? 'danger' : 'warning'}>{row.severity}</Badge> },
      status: { key: 'status', header: 'Status', render: (row: any) => <Badge tone={row.status === 'pass' ? 'success' : row.status === 'warn' ? 'warning' : 'danger'}>{row.status}</Badge> },
      checked: { key: 'checked', header: 'Checked', align: 'right', hideBelow: 'md', render: (row: any) => formatNumber(row.records_checked ?? 0) },
    },
    catalog: {
      sku: { key: 'sku', header: 'SKU', render: (row: any) => <span className="font-mono text-xs">{row.catalog_sku}</span> },
      name: { key: 'name', header: 'Catalog name', hideBelow: 'sm', render: (row: any) => <span className="block max-w-[16rem] truncate">{row.catalog_name}</span> },
      scraped: { key: 'scraped', header: 'Scraped product', render: (row: any) => <span className="block max-w-[18rem] truncate">{row.scraped_name ?? '—'}</span> },
      catalog_price: { key: 'catalog_price', header: 'Our price', align: 'right', render: (row: any) => formatPrice(row.catalog_price) },
      market_price: { key: 'market_price', header: 'Market', align: 'right', render: (row: any) => formatPrice(row.scraped_price_usd) },
      gap: { key: 'gap', header: 'Gap', align: 'right', render: (row: any) => <DeltaPill value={row.price_gap_pct} /> },
      status: { key: 'status', header: 'Status', hideBelow: 'md', render: (row: any) => <Badge tone={row.match_status === 'matched' ? 'success' : 'neutral'}>{titleCase(row.match_status ?? 'unknown')}</Badge> },
    },
    new: {
      product: { key: 'product', header: 'Product', render: (row: any) => <span className="block max-w-[20rem] truncate font-medium">{row.canonical_name}</span> },
      category: { key: 'category', header: 'Category', hideBelow: 'sm', render: (row: any) => <Badge tone="neutral">{row.category_name ?? '—'}</Badge> },
      brand: { key: 'brand', header: 'Brand', hideBelow: 'md', render: (row: any) => row.brand ?? '—' },
      price: { key: 'price', header: 'First price', align: 'right', render: (row: any) => formatPrice(row.price_usd ?? row.first_seen_price_usd) },
      source: { key: 'source', header: 'Source', hideBelow: 'xl', render: (row: any) => <Badge tone="neutral">{row.source_code ?? '—'}</Badge> },
      first_seen: { key: 'first_seen', header: 'First seen', align: 'right', hideBelow: 'lg', render: (row: any) => formatRelative(row.first_seen_at) },
    },
    removed: {
      product: { key: 'product', header: 'Product', render: (row: any) => <span className="block max-w-[20rem] truncate">{row.canonical_name}</span> },
      category: { key: 'category', header: 'Category', hideBelow: 'sm', render: (row: any) => <Badge tone="neutral">{row.category_name ?? '—'}</Badge> },
      source: { key: 'source', header: 'Source', render: (row: any) => <Badge tone="neutral">{row.source_code ?? '—'}</Badge> },
      last_price: { key: 'last_price', header: 'Last price', align: 'right', render: (row: any) => formatPrice(row.last_known_price_usd) },
      missing_days: { key: 'missing_days', header: 'Missing', align: 'right', render: (row: any) => `${row.days_missing ?? '—'}d` },
    },
    movers: {
      product: { key: 'product', header: 'Product', render: (row: any) => <span className="block max-w-[20rem] truncate">{row.canonical_name}</span> },
      from: { key: 'from', header: 'From', align: 'right', render: (row: any) => formatPrice(row.previous_price) },
      to: { key: 'to', header: 'To', align: 'right', render: (row: any) => formatPrice(row.new_price) },
      change: { key: 'change', header: 'Change', align: 'right', render: (row: any) => <DeltaPill value={row.change_pct} /> },
      direction: { key: 'direction', header: 'Direction', hideBelow: 'md', render: (row: any) => <Badge tone={row.direction === 'decrease' ? 'success' : 'danger'}>{titleCase(row.direction)}</Badge> },
      band: { key: 'band', header: 'Band', hideBelow: 'lg', render: (row: any) => <Badge tone="neutral">{row.magnitude_band ?? '—'}</Badge> },
    },
    sources: {
      source: { key: 'source', header: 'Source', render: (row: any) => <span className="font-medium">{row.source_code ?? row.source_name}</span> },
      kind: { key: 'kind', header: 'Kind', hideBelow: 'sm', render: (row: any) => <Badge tone="neutral">{row.kind ?? '—'}</Badge> },
      products: { key: 'products', header: 'Products', align: 'right', render: (row: any) => formatNumber(row.products_seen ?? row.product_count ?? 0) },
      observations: { key: 'observations', header: 'Obs.', align: 'right', render: (row: any) => formatNumber(row.observations ?? 0) },
      success: { key: 'success', header: 'Success', align: 'right', render: (row: any) => `${Number(row.success_rate_pct ?? 0).toFixed(1)}%` },
    },
    categories: {
      category: { key: 'category', header: 'Category', render: (row: any) => <Badge tone="neutral">{row.category_name ?? '—'}</Badge> },
      observations: { key: 'observations', header: 'Obs.', align: 'right', render: (row: any) => formatNumber(row.observations ?? 0) },
      avg_price: { key: 'avg_price', header: 'Avg price', align: 'right', render: (row: any) => formatPrice(row.avg_price) },
      rating: { key: 'rating', header: 'Rating', align: 'center', hideBelow: 'sm', render: (row: any) => (row.avg_rating ? Number(row.avg_rating).toFixed(1) : '—') },
      new_products: { key: 'new_products', header: 'New', align: 'right', hideBelow: 'md', render: (row: any) => formatNumber(row.new_products ?? 0) },
      price_changes: { key: 'price_changes', header: 'Changes', align: 'right', hideBelow: 'md', render: (row: any) => formatNumber(row.price_changes ?? 0) },
    },
    brands: {
      brand: { key: 'brand', header: 'Brand', render: (row: any) => <span className="font-medium">{row.brand ?? '—'}</span> },
      category: { key: 'category', header: 'Category', hideBelow: 'sm', render: (row: any) => <Badge tone="neutral">{row.category_name ?? '—'}</Badge> },
      products: { key: 'products', header: 'Products', align: 'right', render: (row: any) => formatNumber(row.product_count ?? 0) },
      avg_price: { key: 'avg_price', header: 'Avg price', align: 'right', render: (row: any) => formatPrice(row.avg_price_usd) },
      rating: { key: 'rating', header: 'Rating', align: 'center', hideBelow: 'sm', render: (row: any) => (row.avg_rating ? Number(row.avg_rating).toFixed(1) : '—') },
      last_seen: { key: 'last_seen', header: 'Last seen', align: 'right', hideBelow: 'lg', render: (row: any) => formatRelative(row.last_seen_at) },
    },
    availability: {
      category: { key: 'category', header: 'Category', render: (row: any) => <Badge tone="neutral">{row.category_name ?? '—'}</Badge> },
      observations: { key: 'observations', header: 'Obs.', align: 'right', render: (row: any) => formatNumber(row.observations ?? 0) },
      in_stock: { key: 'in_stock', header: 'In-stock', align: 'right', render: (row: any) => `${Number(row.in_stock_pct ?? 0).toFixed(1)}%` },
      out_of_stock: { key: 'out_of_stock', header: 'Out of stock', align: 'right', hideBelow: 'sm', render: (row: any) => formatNumber(row.out_of_stock_count ?? 0) },
    },
  }
  return Object.entries(all[entity])
    .filter(([key]) => has(key))
    .map(([, column]) => (isPinned(column.key) ? { ...column, pinned: true } : column))
}