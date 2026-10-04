import { useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Database, Download, Play, ScanSearch, Table2, Terminal } from 'lucide-react'

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
  type Column,
} from '@/components/ui'
import { ApiError, endpoints } from '@/lib/api'
import { useApiQuery } from '@/hooks/useApi'
import { downloadCsv, formatDuration, formatNumber, truncate } from '@/lib/format'

const DEFAULT_SQL = [
  'SELECT source_code, COUNT(*) AS observations,',
  '       ROUND(AVG(price_usd), 2) AS avg_price_usd',
  'FROM vw_price_snapshots',
  'WHERE observed_at >= CURRENT_DATE - 30',
  'GROUP BY source_code',
  'ORDER BY observations DESC;',
].join('\n')

const LIMITS = [50, 100, 200, 500, 1000, 5000]

type ResultRow = Record<string, unknown>

function renderCell(value: unknown) {
  if (value === null || value === undefined) return <span className="text-subtle">{'—'}</span>
  if (typeof value === 'boolean') return <Badge tone={value ? 'success' : 'neutral'}>{value ? 'true' : 'false'}</Badge>
  if (typeof value === 'number') return <span className="tabular-nums">{value.toLocaleString()}</span>
  if (typeof value === 'object') {
    const text = JSON.stringify(value)
    return (
      <span className="font-mono text-[11px] text-muted" title={text}>
        {truncate(text, 48)}
      </span>
    )
  }
  const text = String(value)
  return (
    <span className="block max-w-[22rem] truncate" title={text}>
      {text}
    </span>
  )
}

function compare(a: unknown, b: unknown, dir: 'asc' | 'desc') {
  if (a === b) return 0
  if (a === null || a === undefined) return 1
  if (b === null || b === undefined) return -1
  const result =
    typeof a === 'number' && typeof b === 'number'
      ? a - (b as number)
      : String(a).localeCompare(String(b), undefined, { numeric: true })
  return dir === 'asc' ? result : -result
}

export default function QueryLab() {
  const [sql, setSql] = useState(DEFAULT_SQL)
  const [limit, setLimit] = useState(200)
  const [sortBy, setSortBy] = useState<string | undefined>()
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
  const editorRef = useRef<HTMLTextAreaElement | null>(null)

  const views = useApiQuery(['query-views'], endpoints.views)
  const tables = useApiQuery(['query-tables'], endpoints.queryTables)
  const examples = useApiQuery(['query-examples'], endpoints.queryExamples)

  const run = useMutation({ mutationFn: () => endpoints.executeQuery(sql, limit) })

  const result = run.data
  const columns = useMemo<string[]>(() => (result?.columns ?? []).slice(), [result])

  const rows = useMemo<ResultRow[]>(() => {
    const raw: unknown[][] = result?.rows ?? []
    return raw.map((line) => {
      const record: ResultRow = {}
      columns.forEach((column, index) => {
        record[column] = line[index]
      })
      return record
    })
  }, [result, columns])

  const sortedRows = useMemo(() => {
    if (!sortBy) return rows
    return rows.slice().sort((a, b) => compare(a[sortBy], b[sortBy], sortDir))
  }, [rows, sortBy, sortDir])

  function execute() {
    run.mutate()
  }

  // The shortcut lives on the editor card so it works from the textarea, the limit
  // selector and the run button without hijacking keys elsewhere on the page.
  function onEditorKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (!(event.metaKey || event.ctrlKey) || event.key !== 'Enter') return
    event.preventDefault()
    execute()
  }

  function onSort(key: string) {
    if (sortBy === key) {
      setSortDir((current) => (current === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortBy(key)
      setSortDir('asc')
    }
  }

  function loadExample(example: any) {
    setSql(String(example?.sql ?? ''))
    setSortBy(undefined)
    run.reset()
  }

  function reference(name: string) {
    const trimmed = sql.trim()
    setSql(trimmed ? `${trimmed.replace(/;?\s*$/, '')}\n-- reference: ${name}\n` : `-- reference: ${name}\n`)
    editorRef.current?.focus()
  }

  function exportCsv() {
    if (!columns.length) return
    const body = sortedRows.map((row) => columns.map((column) => row[column]))
    downloadCsv(
      'query-result.csv',
      [columns, ...body]
        .map((line) => line.map((cell) => `"${String(cell ?? '').replace(/"/g, '""')}"`).join(','))
        .join('\n'),
    )
  }

  const tableColumns: Column<ResultRow>[] = columns.map((column) => ({
    key: column,
    header: column,
    sortValue: (row) => {
      const value = row[column]
      if (typeof value === 'number') return value
      if (typeof value === 'boolean') return value ? 1 : 0
      return value === null || value === undefined ? null : String(value)
    },
    render: (row) => renderCell(row[column]),
  }))

  const groups: [string, string[]][] = Object.entries(tables.data?.groups ?? {})

  return (
    <div className="grid grid-cols-1 items-start gap-3 xl:grid-cols-[minmax(0,24rem)_minmax(0,1fr)]">
      {/* ------------------------------------------------------------- editor */}
      <div className="space-y-3">
        <Card>
          <div onKeyDown={onEditorKeyDown}>
            <CardHeader
              title="SQL editor"
              subtitle="Read-only: SELECT, WITH and EXPLAIN are accepted, anything else is rejected."
              icon={<Terminal className="h-4 w-4" />}
              action={
                <kbd className="rounded border border-line bg-surface-3 px-1.5 py-0.5 font-mono text-[10px] text-subtle">
                  Ctrl/Cmd + Enter
                </kbd>
              }
            />
            <textarea
              ref={editorRef}
              value={sql}
              onChange={(event) => {
                setSql(event.target.value)
                setSortBy(undefined)
              }}
              rows={10}
              spellCheck={false}
              autoCapitalize="off"
              autoCorrect="off"
              aria-label="SQL statement"
              className="input h-56 w-full resize-y bg-surface-2 font-mono text-[12.5px] leading-relaxed"
            />
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Button
                variant="primary"
                size="sm"
                loading={run.isPending}
                icon={<Play className="h-4 w-4" />}
                onClick={execute}
              >
                Run query
              </Button>
              <Select
                value={String(limit)}
                onChange={(event) => setLimit(Number(event.target.value))}
                aria-label="Row limit"
                className="w-auto"
              >
                {LIMITS.map((value) => (
                  <option key={value} value={value}>
                    {formatNumber(value)} rows max
                  </option>
                ))}
              </Select>
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader title="Starter queries" subtitle="Click to load one into the editor" icon={<ScanSearch className="h-4 w-4" />} />
          {examples.isError ? (
            <ErrorState message={(examples.error as Error)?.message} onRetry={() => examples.refetch()} />
          ) : examples.isLoading && !examples.data ? (
            <LoadingState label={'Loading starter queries…'} rows={2} />
          ) : examples.data?.length ? (
            <ul className="space-y-1.5">
              {examples.data.map((example: any) => (
                <li key={example.title}>
                  <button
                    onClick={() => loadExample(example)}
                    className="w-full rounded-lg border border-line px-3 py-2 text-left hover:border-line-strong hover:bg-surface-2"
                  >
                    <span className="block text-xs font-medium text-ink">{example.title}</span>
                    <span className="mt-0.5 block truncate font-mono text-[10px] text-subtle">{example.sql}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="No starter query available" />
          )}
        </Card>

        <Card>
          <CardHeader
            title="Analytical views"
            subtitle="Click a view to leave a reference comment in the editor"
            icon={<Table2 className="h-4 w-4" />}
          />
          {views.isError ? (
            <ErrorState message={(views.error as Error)?.message} onRetry={() => views.refetch()} />
          ) : views.isLoading && !views.data ? (
            <LoadingState label={'Loading views…'} rows={2} />
          ) : views.data?.length ? (
            <div className="flex max-h-48 flex-wrap gap-1.5 overflow-auto">
              {views.data.map((view: any) => (
                <button
                  key={view.name}
                  onClick={() => reference(String(view.name))}
                  className="rounded-full border border-line bg-surface px-2.5 py-1 font-mono text-[11px] text-muted hover:border-line-strong hover:text-ink"
                >
                  {view.name}
                </button>
              ))}
            </div>
          ) : (
            <EmptyState title="No analytical view found" message="The warehouse exposes no view yet." />
          )}
        </Card>

        {/* -------------------------------------------------- schema browser */}
        <Card>
          <CardHeader
            title="Schema browser"
            subtitle={`${formatNumber(tables.data?.tables?.length ?? 0)} tables in ${groups.length} logical groups`}
            icon={<Database className="h-4 w-4" />}
          />
          {tables.isError ? (
            <ErrorState message={(tables.error as Error)?.message} onRetry={() => tables.refetch()} />
          ) : tables.isLoading && !tables.data ? (
            <LoadingState label={'Loading schema…'} rows={3} />
          ) : groups.length ? (
            <div className="space-y-3">
              {groups.map(([group, names]) => (
                <div key={group}>
                  <p className="stat-label mb-1.5">{group}</p>
                  <div className="flex flex-wrap gap-1">
                    {names.map((name) => (
                      <button
                        key={name}
                        onClick={() => reference(name)}
                        className="rounded-md border border-line bg-surface px-2 py-1 font-mono text-[11px] text-muted hover:border-line-strong hover:text-ink"
                      >
                        {name}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
              <p className="border-t border-line pt-2 text-[11px] leading-relaxed text-subtle">
                The console runs on a read-only connection: no DDL, no DML and one statement per query.
              </p>
            </div>
          ) : (
            <EmptyState title="No schema published" message="The API returned no table group." />
          )}
        </Card>
      </div>

      {/* ------------------------------------------------------------ results */}
      <Card padded={false}>
        <div className="p-4 sm:p-5">
          <CardHeader
            title="Result set"
            subtitle={result ? `${columns.length} column${columns.length === 1 ? '' : 's'} returned` : 'Run a statement to see rows'}
            icon={<Database className="h-4 w-4" />}
            action={
              result ? (
                <Button size="sm" variant="secondary" icon={<Download className="h-4 w-4" />} onClick={exportCsv}>
                  CSV
                </Button>
              ) : null
            }
          />
          {result ? (
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="info">{formatNumber(result.row_count ?? 0)} rows</Badge>
              <Badge tone="neutral">{formatDuration(result.duration_ms ?? 0)}</Badge>
              {result.truncated ? (
                <Badge tone="warning">truncated at {formatNumber(limit)} rows</Badge>
              ) : (
                <Badge tone="success">complete</Badge>
              )}
            </div>
          ) : null}
        </div>

        {run.isError ? (
          <div className="space-y-2 p-4">
            <QueryError error={run.error} />
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="secondary" onClick={execute}>
                Run again
              </Button>
              <Button size="sm" variant="ghost" onClick={() => run.reset()}>
                Dismiss
              </Button>
            </div>
          </div>
        ) : run.isPending ? (
          <div className="p-4">
            <LoadingState label={'Running the statement…'} rows={6} />
          </div>
        ) : !result ? (
          <EmptyState
            title="Nothing executed yet"
            message="Write a statement or load one of the starter queries, then press Ctrl+Enter."
            icon={<Play className="h-7 w-7" />}
          />
        ) : !rows.length ? (
          <EmptyState
            title="The statement returned no row"
            message="The SQL was accepted but matched nothing. Check the WHERE clause or widen the date window."
          />
        ) : (
          <DataTable
            rows={sortedRows}
            rowKey={(_, index) => String(index)}
            onSort={onSort}
            sort={sortBy ? { by: sortBy, dir: sortDir } : undefined}
            maxHeight="34rem"
            dense
            emptyMessage="The statement returned no row"
            columns={tableColumns}
          />
        )}
      </Card>
    </div>
  )
}

/* ------------------------------------------------------------------ error copy */
function QueryError({ error }: { error: Error | null }) {
  if (error instanceof ApiError) {
    const details = error.details as { errors?: { message?: string }[] } | undefined
    const reasons = (details?.errors ?? [])
      .map((item) => item.message)
      .filter(Boolean)
      .join(' ')
    if (error.status === 422) {
      return (
        <div role="alert" className="rounded-lg border border-danger/40 bg-danger-soft p-3">
          <p className="text-sm font-semibold text-danger">Statement rejected by the read-only guard</p>
          <p className="mt-1 text-xs text-ink">{reasons || error.message}</p>
          <p className="mt-1 text-[11px] text-muted">
            A single SELECT, WITH or EXPLAIN statement is accepted; writes, DDL and semicolon-separated batches are refused.
          </p>
        </div>
      )
    }
    return (
      <div role="alert" className="rounded-lg border border-danger/40 bg-danger-soft p-3">
        <p className="text-sm font-semibold text-danger">The query failed (HTTP {error.status})</p>
        <p className="mt-1 text-xs text-ink">{error.message}</p>
        <p className="mt-1 text-[11px] text-muted">
          Error code <span className="font-mono">{error.code}</span> - check the table and column names against the schema browser.
        </p>
      </div>
    )
  }
  return <ErrorState title="The query could not be sent" message={error?.message ?? 'Unknown error'} />
}
