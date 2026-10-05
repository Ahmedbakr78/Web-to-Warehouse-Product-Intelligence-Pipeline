/**
 * Aggregate builder - server-side group-by, aggregation and advanced filtering.
 *
 * Unlike the filter-first "Rows" mode, this composes a structured query that the API
 * compiles into a parameterised SELECT (POST /builder/query). It supports grouping,
 * six aggregate functions, fifteen operators and a live chart preview.
 */

import { useMemo, useState } from 'react'
import { BarChart3, Copy, Download, Layers, Play, Plus, RotateCcw, Terminal, Trash2 } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'

import { useDebounce } from '@/hooks/useDebounce'
import {
  Badge,
  Button,
  Card,
  CardHeader,
  DataTable,
  EmptyState,
  ErrorState,
  LoadingState,
  Select,
  TextInput,
  Toggle,
  useToast,
} from '@/components/ui'
import { BarSeries } from '@/components/charts'
import { endpoints } from '@/lib/api'
import { formatNumber, toCsv, downloadCsv, downloadJson, titleCase } from '@/lib/format'

type FilterRow = { id: number; column: string; operator: string; value: string; value2: string }
type AggRow = { id: number; function: string; column: string; alias: string }

type SchemaEntity = {
  entity: string
  label: string
  columns: { name: string; type: string; groupable: boolean }[]
}
type Schema = {
  entities: SchemaEntity[]
  operators: { operator: string; sql: string; value_type: string }[]
  aggregates: string[]
}
type QueryResult = {
  columns: string[]
  rows: (string | number | null)[][]
  row_count: number
  total: number
  duration_ms: number
  sql_preview: string
}

const AGG_LABELS: Record<string, string> = {
  count: 'Count rows',
  count_distinct: 'Count distinct',
  sum: 'Sum',
  avg: 'Average',
  min: 'Minimum',
  max: 'Maximum',
}
const OP_LABELS: Record<string, string> = {
  eq: 'equals',
  ne: 'not equal',
  gt: 'greater than',
  gte: 'at least',
  lt: 'less than',
  lte: 'at most',
  contains: 'contains',
  not_contains: 'excludes',
  starts_with: 'starts with',
  ends_with: 'ends with',
  in: 'in list',
  not_in: 'not in list',
  between: 'between',
  empty: 'is empty',
  not_empty: 'is not empty',
}

let nextId = 1
const makeFilter = (): FilterRow => ({ id: nextId++, column: '', operator: 'eq', value: '', value2: '' })
const makeAgg = (): AggRow => ({ id: nextId++, function: 'count', column: '', alias: '' })

/** Render one aggregate cell: the grouping key as text, measures as numbers. */
function renderCell(value: unknown) {
  if (value === null || value === undefined || value === '') return <span className="text-subtle">—</span>
  if (typeof value === 'number') return <span className="font-medium tabular-nums">{formatNumber(value, 2)}</span>
  return <span className="block max-w-[18rem] truncate">{String(value)}</span>
}

export default function AggregateBuilder() {
  const toast = useToast()
  const schemaQuery = useQuery({ queryKey: ['builder-schema'], queryFn: endpoints.builderSchema, staleTime: 900_000 })
  const schema = schemaQuery.data as Schema | undefined

  const [entity, setEntity] = useState('products')
  const [groupBy, setGroupBy] = useState('')
  const [aggregates, setAggregates] = useState<AggRow[]>([makeAgg()])
  const [filters, setFilters] = useState<FilterRow[]>([])
  const [sortColumn, setSortColumn] = useState('')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [limit, setLimit] = useState(25)
  const [showChart, setShowChart] = useState(true)

  const current = useMemo(() => schema?.entities.find((item) => item.entity === entity), [schema, entity])
  const numericColumns = useMemo(() => current?.columns.filter((column) => column.type === 'number') ?? [], [current])
  const groupableColumns = useMemo(() => current?.columns.filter((column) => column.groupable) ?? [], [current])

  // Default the grouping and sort to the first sensible choice when the entity changes.
  const effectiveGroupBy = groupBy || groupableColumns[0]?.name || ''
  const hasAgg = aggregates.some((agg) => agg.function)
  const aggAlias = (agg: AggRow) => agg.alias || `${agg.function}_${agg.column || 'all'}`

  const payload = useMemo(() => {
    const usedAggregates = aggregates
      .filter((agg) => agg.function)
      .map((agg) => ({
        function: agg.function,
        column: agg.function === 'count' ? null : agg.column || null,
        alias: agg.alias || undefined,
      }))
    return {
      entity,
      group_by: effectiveGroupBy ? [effectiveGroupBy] : [],
      aggregates: usedAggregates,
      filters: filters
        .filter((row) => row.column && row.operator)
        .map((row) => ({
          column: row.column,
          operator: row.operator,
          value: coerce(row.value, row.operator),
          value2: coerce(row.value2, row.operator),
        })),
      sort: sortColumn ? [{ column: sortColumn, direction: sortDir }] : [],
      limit,
    }
  }, [entity, effectiveGroupBy, aggregates, filters, sortColumn, sortDir, limit])

  // Debounced so typing a filter value does not fire a request per keystroke.
  const debouncedPayload = useDebounce(payload, 320)

  const query = useQuery({
    queryKey: ['builder-aggregate', debouncedPayload],
    queryFn: () => endpoints.builderQuery(debouncedPayload),
    enabled: Boolean(entity && effectiveGroupBy && hasAgg),
    placeholderData: (previous) => previous,
  })

  const result = query.data as QueryResult | undefined
  const metricColumn = useMemo(() => {
    if (!result?.columns) return ''
    const numeric = result.columns.find((column) => column !== effectiveGroupBy && typeof result.rows[0]?.[result.columns.indexOf(column)] !== 'string')
    return numeric ?? ''
  }, [result, effectiveGroupBy])

  function coerce(value: string, operator: string): unknown {
    if (operator === 'empty' || operator === 'not_empty') return null
    if (operator === 'in' || operator === 'not_in') return value.split(',').map((item) => item.trim()).filter(Boolean)
    if (operator === 'between') return value
    if (value === '') return null
    const asNumber = Number(value)
    return value !== '' && !Number.isNaN(asNumber) ? asNumber : value
  }

  function reset() {
    setGroupBy('')
    setAggregates([makeAgg()])
    setFilters([])
    setSortColumn('')
    setSortDir('desc')
    setLimit(25)
    setDraft((value) => value + 1)
  }

  function exportResult(format: 'csv' | 'json') {
    if (!result) return
    if (format === 'csv') downloadCsv(`aggregate-${entity}.csv`, toCsv(result.columns, result.rows))
    else downloadJson(`aggregate-${entity}.json`, { query: payload, result })
  }

  function copyCurl() {
    if (!result) return
    const curl = `curl -X POST ${import.meta.env.VITE_API_BASE_URL ?? '/api/v1'}/builder/query \\
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \\
  -d '${JSON.stringify(payload)}'`
    navigator.clipboard?.writeText(curl).then(
      () => toast.success('cURL copied'),
      () => toast.error('Clipboard unavailable'),
    )
  }

  if (schemaQuery.isLoading) return <LoadingState label="Loading builder schema…" rows={4} />
  if (schemaQuery.isError) return <ErrorState message={(schemaQuery.error as Error)?.message} onRetry={() => schemaQuery.refetch()} />

  const chartData = (result?.rows ?? []).slice(0, 20).map((row) => {
    const record: Record<string, unknown> = {}
    result!.columns.forEach((column, index) => {
      record[column] = row[index]
    })
    return record
  })

  return (
    <div className="space-y-4">
      {/* ------------------------------------------------------------- header */}
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <CardHeader
              title="Aggregate builder"
              subtitle="Group, measure and filter in the warehouse - compiled to a safe parameterised SELECT"
              icon={<Layers className="h-4 w-4" />}
            />
          </div>
          <div className="flex shrink-0 gap-2">
            <Button size="sm" variant="ghost" icon={<Copy className="h-4 w-4" />} onClick={copyCurl} disabled={!result}>
              Copy cURL
            </Button>
            <Button size="sm" variant="secondary" icon={<RotateCcw className="h-4 w-4" />} onClick={reset}>
              Reset
            </Button>
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-4">
        {/* ------------------------------------------------------------- query */}
        <Card className="xl:col-span-3">
          <CardHeader title="Query" subtitle="Pick a dataset, group it and add measures" icon={<BarChart3 className="h-4 w-4" />} />
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <p className="stat-label mb-1.5">Dataset</p>
              <Select
                value={entity}
                onChange={(event) => {
                  setEntity(event.target.value)
                  setGroupBy('')
                  setSortColumn('')
                  setAggregates([makeAgg()])
                  setDraft((value) => value + 1)
                }}
              >
                {schema?.entities.map((item) => (
                  <option key={item.entity} value={item.entity}>
                    {item.label}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <p className="stat-label mb-1.5">Group by</p>
              <Select value={effectiveGroupBy} onChange={(event) => setGroupBy(event.target.value)}>
                <option value="">No grouping</option>
                {groupableColumns.map((column) => (
                  <option key={column.name} value={column.name}>
                    {titleCase(column.name)}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <p className="stat-label mb-1.5">Sort measure</p>
              <Select
                value={sortColumn}
                onChange={(event) => setSortColumn(event.target.value)}
              >
                <option value="">Default</option>
                {result?.columns.map((column) => (
                  <option key={column} value={column}>
                    {titleCase(column)}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <p className="stat-label mb-1.5">Direction & rows</p>
              <div className="flex gap-1">
                <Select value={sortDir} onChange={(event) => setSortDir(event.target.value as 'asc' | 'desc')} className="w-24">
                  <option value="desc">Desc</option>
                  <option value="asc">Asc</option>
                </Select>
                <Select value={String(limit)} onChange={(event) => setLimit(Number(event.target.value))} className="flex-1">
                  {[10, 25, 50, 100].map((size) => (
                    <option key={size} value={String(size)}>
                      {size} rows
                    </option>
                  ))}
                </Select>
              </div>
            </div>
          </div>

          {/* measures */}
          <div className="mt-4">
            <div className="mb-2 flex items-center justify-between">
              <p className="stat-label">Measures</p>
              <Button size="sm" variant="ghost" icon={<Plus className="h-3.5 w-3.5" />} onClick={() => setAggregates((rows) => [...rows, makeAgg()])}>
                Add measure
              </Button>
            </div>
            <div className="space-y-2">
              {aggregates.map((agg) => (
                <div key={agg.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-surface-2 p-2">
                  <Select
                    value={agg.function}
                    onChange={(event) =>
                      setAggregates((rows) => rows.map((row) => (row.id === agg.id ? { ...row, function: event.target.value } : row)))
                    }
                    className="w-40"
                  >
                    {schema?.aggregates.map((fn) => (
                      <option key={fn} value={fn}>
                        {AGG_LABELS[fn] ?? titleCase(fn)}
                      </option>
                    ))}
                  </Select>
                  {agg.function !== 'count' ? (
                    <Select
                      value={agg.column}
                      onChange={(event) =>
                        setAggregates((rows) => rows.map((row) => (row.id === agg.id ? { ...row, column: event.target.value } : row)))
                      }
                      className="w-44"
                    >
                      <option value="">Choose column…</option>
                      {(agg.function === 'count_distinct' ? current?.columns ?? [] : numericColumns).map((column) => (
                        <option key={column.name} value={column.name}>
                          {titleCase(column.name)}
                        </option>
                      ))}
                    </Select>
                  ) : null}
                  <TextInput
                    value={agg.alias}
                    onChange={(event) =>
                      setAggregates((rows) => rows.map((row) => (row.id === agg.id ? { ...row, alias: event.target.value } : row)))
                    }
                    placeholder={`Label (${aggAlias(agg)})`}
                    className="w-40"
                  />
                  {aggregates.length > 1 ? (
                    <button
                      onClick={() => setAggregates((rows) => rows.filter((row) => row.id !== agg.id))}
                      aria-label="Remove measure"
                      className="rounded p-1.5 text-subtle hover:bg-danger-soft hover:text-danger"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  ) : null}
                </div>
              ))}
            </div>
          </div>

          {/* filters */}
          <div className="mt-4">
            <div className="mb-2 flex items-center justify-between">
              <p className="stat-label">Advanced filters</p>
              <Button size="sm" variant="ghost" icon={<Plus className="h-3.5 w-3.5" />} onClick={() => setFilters((rows) => [...rows, makeFilter()])}>
                Add filter
              </Button>
            </div>
            {filters.length ? (
              <div className="space-y-2">
                {filters.map((row) => (
                  <div key={row.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-surface-2 p-2">
                    <Select
                      value={row.column}
                      onChange={(event) => setFilters((rows) => rows.map((item) => (item.id === row.id ? { ...item, column: event.target.value } : item)))}
                      className="w-40"
                    >
                      <option value="">Column…</option>
                      {(current?.columns ?? []).map((column) => (
                        <option key={column.name} value={column.name}>
                          {titleCase(column.name)}
                        </option>
                      ))}
                    </Select>
                    <Select
                      value={row.operator}
                      onChange={(event) => setFilters((rows) => rows.map((item) => (item.id === row.id ? { ...item, operator: event.target.value } : item)))}
                      className="w-36"
                    >
                      {schema?.operators.map((op) => (
                        <option key={op.operator} value={op.operator}>
                          {OP_LABELS[op.operator] ?? op.operator}
                        </option>
                      ))}
                    </Select>
                    {!['empty', 'not_empty'].includes(row.operator) ? (
                      <>
                        <TextInput
                          value={row.value}
                          onChange={(event) => setFilters((rows) => rows.map((item) => (item.id === row.id ? { ...item, value: event.target.value } : item)))}
                          placeholder={row.operator === 'in' || row.operator === 'not_in' ? 'a, b, c' : row.operator === 'between' ? 'from' : 'value'}
                          className="w-32"
                        />
                        {row.operator === 'between' ? (
                          <TextInput
                            value={row.value2}
                            onChange={(event) => setFilters((rows) => rows.map((item) => (item.id === row.id ? { ...item, value2: event.target.value } : item)))}
                            placeholder="to"
                            className="w-24"
                          />
                        ) : null}
                      </>
                    ) : null}
                    <button
                      onClick={() => setFilters((rows) => rows.filter((item) => item.id !== row.id))}
                      aria-label="Remove filter"
                      className="rounded p-1.5 text-subtle hover:bg-danger-soft hover:text-danger"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-[11px] text-subtle">No filters - the whole dataset is aggregated. Add one to narrow the scope.</p>
            )}
          </div>
        </Card>

        {/* ------------------------------------------------------------- summary */}
        <Card>
          <CardHeader title="Result" subtitle="Live summary" icon={<Play className="h-4 w-4" />} />
          <div className="space-y-3">
            <div className="rounded-lg bg-surface-2 p-3">
              <p className="stat-label">Groups returned</p>
              <p className="stat-value mt-0.5">{formatNumber(result?.row_count ?? 0)}</p>
              <p className="text-[11px] text-subtle">of {formatNumber(result?.total ?? 0)} total</p>
            </div>
            <div className="rounded-lg bg-surface-2 p-3">
              <p className="stat-label">Duration</p>
              <p className="stat-value mt-0.5">{result ? `${result.duration_ms} ms` : '—'}</p>
            </div>
            <div className="rounded-lg bg-surface-2 p-3">
              <p className="stat-label mb-1.5">Measures</p>
              <div className="flex flex-wrap gap-1.5">
                {aggregates.filter((a) => a.function).map((agg) => (
                  <Badge key={agg.id} tone="brand">
                    {aggAlias(agg)}
                  </Badge>
                ))}
              </div>
            </div>
            <Toggle checked={showChart} onChange={setShowChart} label="Show chart" description="Horizontal bar preview" />
            <div className="flex gap-2">
              <Button size="sm" variant="secondary" icon={<Download className="h-3.5 w-3.5" />} onClick={() => exportResult('csv')} disabled={!result?.row_count}>
                CSV
              </Button>
              <Button size="sm" variant="ghost" onClick={() => exportResult('json')} disabled={!result?.row_count}>
                JSON
              </Button>
            </div>
          </div>
        </Card>
      </div>

      {/* ------------------------------------------------------------- chart */}
      {showChart && result?.row_count ? (
        <Card>
          <CardHeader title="Chart preview" subtitle={`${metricColumn || 'measure'} by ${effectiveGroupBy || 'row'}`} icon={<BarChart3 className="h-4 w-4" />} />
          <BarSeries
            data={chartData}
            xKey={effectiveGroupBy || result.columns[0]}
            bars={result.columns
              .filter((column) => column !== effectiveGroupBy)
              .map((column) => ({ key: column, label: titleCase(column) }))}
            height={Math.min(420, 120 + result.row_count * 18)}
            horizontal
          />
        </Card>
      ) : null}

      {/* ------------------------------------------------------------- table */}
      <Card padded={false}>
        <div className="flex flex-wrap items-center justify-between gap-2 p-4 sm:p-5">
          <CardHeader title="Aggregated rows" subtitle="Exactly what the warehouse returned" icon={<Layers className="h-4 w-4" />} />
        </div>
        {query.isError ? (
          <div className="p-4">
            <ErrorState message={(query.error as Error)?.message} onRetry={() => query.refetch()} />
          </div>
        ) : query.isLoading && !result ? (
          <div className="p-4">
            <LoadingState label="Running aggregate query…" rows={4} />
          </div>
        ) : result?.row_count ? (
          <DataTable
            rows={result.rows.map((row) => {
              const record: Record<string, unknown> = {}
              result.columns.forEach((column, index) => {
                record[column] = row[index]
              })
              return record
            })}
            rowKey={(_row: Record<string, unknown>, index: number) => String(index)}
            loading={query.isFetching}
            columns={result.columns.map((column) => ({
              key: column,
              header: titleCase(column),
              align: (column === effectiveGroupBy ? 'left' : 'right') as 'left' | 'right',
              render: (row: Record<string, unknown>) => renderCell(row[column]),
            }))}
          />
        ) : (
          <EmptyState
            icon={<BarChart3 className="h-6 w-6" />}
            title="No aggregation yet"
            message="Choose a dataset and at least one measure to see results."
          />
        )}
      </Card>

      {/* ------------------------------------------------------------- SQL */}
      {result ? (
        <Card>
          <CardHeader title="Generated SQL" subtitle="Read-only, parameterised - safe to copy anywhere" icon={<Terminal className="h-4 w-4" />} />
          <pre className="overflow-x-auto rounded-lg bg-surface-3 p-3 font-mono text-[11px] leading-relaxed text-muted">
            {result.sql_preview}
          </pre>
        </Card>
      ) : null}
    </div>
  )
}