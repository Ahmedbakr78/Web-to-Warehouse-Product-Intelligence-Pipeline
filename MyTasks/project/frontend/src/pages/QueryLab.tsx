import { useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  CheckCircle2,
  Copy,
  Database,
  Download,
  Eraser,
  Play,
  ScanSearch,
  ScrollText,
  Table2,
  Terminal,
  Wand2,
  Wifi,
  WifiOff,
  X,
} from 'lucide-react'

import {
  Badge,
  Button,
  Card,
  CardHeader,
  DataTable,
  EmptyState,
  ErrorState,
  LoadingState,
  SearchInput,
  Select,
  type Column,
} from '@/components/ui'
import QueryHistoryPanel from '@/components/QueryHistoryPanel'
import { API_BASE, ApiError, endpoints } from '@/lib/api'
import { useApiQuery } from '@/hooks/useApi'
import { downloadCsv, formatDuration, formatNumber, truncate } from '@/lib/format'

/* ------------------------------------------------------------------ defaults */

const DEFAULT_SQL = [
  'SELECT source_code, COUNT(*) AS observations,',
  '       ROUND(AVG(price_usd), 2) AS avg_price_usd',
  'FROM vw_price_history',
  'WHERE captured_at >= CURRENT_DATE - 30',
  'GROUP BY source_code',
  'ORDER BY observations DESC;',
].join('\n')

const LIMITS = [50, 100, 200, 500, 1000, 5000]
const SQL_KEY = 'pip.query.sql'
const LIMIT_KEY = 'pip.query.limit'
const RECENT_KEY = 'pip.query.recent'

const FORBIDDEN_TABLES = ['app_user', 'app_api_key', 'app_session', 'app_webhook'] as const
const WRITE_KEYWORDS = [
  'insert',
  'update',
  'delete',
  'drop',
  'alter',
  'create',
  'truncate',
  'grant',
  'revoke',
  'commit',
  'rollback',
  'replace',
  'merge',
  'call',
  'vacuum',
  'attach',
  'detach',
  'copy',
] as const

type ResultRow = Record<string, unknown>

/* ------------------------------------------------------- client-side guard
   Mirrors app/api/query_guard.py so the editor can warn before the round-trip.
   Mask strings/comments, then check first keyword, semicolons and writes. */

function maskSql(sql: string): { masked: string; semicolons: number[] } {
  const masked = sql.split('')
  const semicolons: number[] = []
  const n = sql.length
  let i = 0
  let single = false
  let double = false
  let backtick = false
  let lineComment = false
  let blockComment = false
  const blank = (pos: number) => {
    if (masked[pos] !== '\n') masked[pos] = ' '
  }
  while (i < n) {
    const ch = sql[i]
    const nxt = i + 1 < n ? sql[i + 1] : ''
    if (lineComment) {
      blank(i)
      if (ch === '\n') lineComment = false
      i += 1
      continue
    }
    if (blockComment) {
      blank(i)
      if (ch === '*' && nxt === '/') {
        blank(i + 1)
        i += 2
        blockComment = false
      } else {
        i += 1
      }
      continue
    }
    if (single) {
      blank(i)
      if (ch === '\\' && i + 1 < n) {
        blank(i + 1)
        i += 2
        continue
      }
      if (ch === "'") {
        if (nxt === "'") {
          blank(i + 1)
          i += 2
          continue
        }
        single = false
      }
      i += 1
      continue
    }
    if (double) {
      blank(i)
      if (ch === '\\' && i + 1 < n) {
        blank(i + 1)
        i += 2
        continue
      }
      if (ch === '"') {
        if (nxt === '"') {
          blank(i + 1)
          i += 2
          continue
        }
        double = false
      }
      i += 1
      continue
    }
    if (backtick) {
      blank(i)
      if (ch === '`') backtick = false
      i += 1
      continue
    }
    if (ch === '-' && nxt === '-') {
      blank(i)
      blank(i + 1)
      lineComment = true
      i += 2
      continue
    }
    if (ch === '/' && nxt === '*') {
      blank(i)
      blank(i + 1)
      blockComment = true
      i += 2
      continue
    }
    if (ch === "'") {
      blank(i)
      single = true
      i += 1
      continue
    }
    if (ch === '"') {
      blank(i)
      double = true
      i += 1
      continue
    }
    if (ch === '`') {
      blank(i)
      backtick = true
      i += 1
      continue
    }
    if (ch === ';') semicolons.push(i)
    i += 1
  }
  return { masked: masked.join(''), semicolons }
}

function validateClient(sql: string): { ok: boolean; reason: string } {
  if (!sql.trim()) return { ok: false, reason: 'The editor is empty.' }
  const { masked, semicolons } = maskSql(sql)
  if (semicolons.length > 1) return { ok: false, reason: 'Only one statement per query.' }
  if (semicolons.length === 1) {
    const after = masked.slice(semicolons[0] + 1)
    if (after.trim()) return { ok: false, reason: 'Only one statement per query.' }
  }
  let leading = masked.trimStart()
  while (leading.startsWith('(')) leading = leading.slice(1).trimStart()
  const first = /^(select|with|explain)\b/i.exec(leading)
  if (!first) return { ok: false, reason: 'Start with SELECT, WITH or EXPLAIN.' }
  const write = new RegExp(`\\b(${WRITE_KEYWORDS.join('|')})\\b`, 'i').exec(masked)
  if (write) return { ok: false, reason: `Writes are rejected (${write[1].toUpperCase()}).` }
  if (/\binto\b/i.test(masked)) return { ok: false, reason: 'SELECT ... INTO is rejected.' }
  if (/\bfor\s+(update|share|no\s+key\s+update)\b/i.test(masked)) {
    return { ok: false, reason: 'Locking reads are rejected.' }
  }
  for (const table of FORBIDDEN_TABLES) {
    if (new RegExp(`\\b${table}\\b`, 'i').test(masked)) {
      return { ok: false, reason: `Table '${table}' is not queryable.` }
    }
  }
  return { ok: true, reason: 'Read-only check passed.' }
}

/* ------------------------------------------------------- highlighting */

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

const HIGHLIGHT_RE =
  /(--[^\n]*)|(\/\*[\s\S]*?(?:\*\/|$))|('(?:[^'\\]|\\.|'')*'(?:$)?|"(?:[^"\\]|\\.|"")*"(?:$)?|`(?:[^`\\]|\\.)*`?(?:$)?)|\b(\d+(?:\.\d+)?)\b|\b(SELECT|WITH|EXPLAIN|FROM|WHERE|GROUP\s+BY|ORDER\s+BY|HAVING|LIMIT|OFFSET|AS|ON|USING|JOIN|LEFT|RIGHT|INNER|OUTER|FULL|CROSS|AND|OR|NOT|IN|IS|NULL|LIKE|ILIKE|BETWEEN|EXISTS|CASE|WHEN|THEN|ELSE|END|DISTINCT|UNION|ALL|INTERVAL|ASC|DESC|CURRENT_DATE|CURRENT_TIMESTAMP|NOW)\b|\b(COUNT|AVG|SUM|MIN|MAX|ROUND|ABS|COALESCE|NULLIF|CAST|EXTRACT|DATE|DATEDIFF|STDDEV|SQRT|LAG|LEAD|ROW_NUMBER|RANK)\b/gi

function highlightSql(sql: string): string {
  // Trailing newline keeps the <pre> the same height as the textarea.
  const source = sql.endsWith('\n') ? `${sql} ` : sql
  return escapeHtml(source).replace(HIGHLIGHT_RE, (match, comment, block, str, num, kw, fn) => {
    if (comment ?? block) return `<span class="sql-comment">${match}</span>`
    if (str) return `<span class="sql-string">${match}</span>`
    if (num) return `<span class="sql-number">${match}</span>`
    if (kw) return `<span class="sql-keyword">${match}</span>`
    if (fn) return `<span class="sql-fn">${match}</span>`
    return match
  })
}

function formatSql(sql: string): string {
  let out = sql.trim().replace(/;[ \t]*$/, '')
  const breaks = [
    'FROM',
    'LEFT JOIN',
    'LEFT OUTER JOIN',
    'RIGHT JOIN',
    'INNER JOIN',
    'OUTER JOIN',
    'FULL JOIN',
    'CROSS JOIN',
    'JOIN',
    'WHERE',
    'GROUP BY',
    'HAVING',
    'ORDER BY',
    'LIMIT',
    'OFFSET',
    'UNION ALL',
    'UNION',
  ]
  for (const key of breaks) {
    out = out.replace(new RegExp(`\\s+${key.replace(/ /g, '\\s+')}\\s+`, 'gi'), `\n${key}\n  `)
  }
  out = out.replace(/\s+(AND|OR)\s+/gi, '\n  $1 ')
  // Uppercase the structural keywords, keep identifiers untouched.
  out = out.replace(
    /\b(select|with|explain|from|where|group by|order by|having|limit|offset|as|on|join|left|right|inner|outer|full|cross|and|or|not|in|is|null|like|between|exists|case|when|then|else|end|distinct|union|all|having|asc|desc)\b/gi,
    (word) => word.toUpperCase(),
  )
  return `${out.replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim()};`
}

/* ------------------------------------------------------- cells */

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

function loadStored(key: string, fallback: string): string {
  try {
    return localStorage.getItem(key) ?? fallback
  } catch {
    return fallback
  }
}

/* ------------------------------------------------------- page */

export default function QueryLab() {
  const queryClient = useQueryClient()
  const [sql, setSql] = useState(() => loadStored(SQL_KEY, DEFAULT_SQL))
  const [limit, setLimit] = useState(() => {
    const raw = loadStored(LIMIT_KEY, '200')
    const parsed = Number(raw)
    return LIMITS.includes(parsed) ? parsed : 200
  })
  const [sortBy, setSortBy] = useState<string | undefined>()
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
  const [resultFilter, setResultFilter] = useState('')
  const editorRef = useRef<HTMLTextAreaElement | null>(null)
  const highlightRef = useRef<HTMLPreElement | null>(null)
  const gutterRef = useRef<HTMLDivElement | null>(null)

  const views = useApiQuery(['query-views'], endpoints.views)
  const tables = useApiQuery(['query-tables'], endpoints.queryTables)
  const examples = useApiQuery(['query-examples'], endpoints.queryExamples)

  const run = useMutation({
    mutationFn: (overrideSql?: string) => endpoints.executeQuery(overrideSql ?? sql, limit),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['query-history'] })
      try {
        const recent = JSON.parse(localStorage.getItem(RECENT_KEY) ?? '[]') as string[]
        const next = [sql.slice(0, 20000), ...recent.filter((item) => item !== sql)].slice(0, 20)
        localStorage.setItem(RECENT_KEY, JSON.stringify(next))
      } catch {
        /* private mode - history simply stays server-side */
      }
    },
  })

  useEffect(() => {
    try {
      localStorage.setItem(SQL_KEY, sql)
    } catch {
      /* ignore */
    }
  }, [sql])

  useEffect(() => {
    try {
      localStorage.setItem(LIMIT_KEY, String(limit))
    } catch {
      /* ignore */
    }
  }, [limit])

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

  const filteredRows = useMemo(() => {
    const needle = resultFilter.trim().toLowerCase()
    if (!needle) return rows
    return rows.filter((row) =>
      columns.some((column) => String(row[column] ?? '').toLowerCase().includes(needle)),
    )
  }, [rows, columns, resultFilter])

  const sortedRows = useMemo(() => {
    if (!sortBy) return filteredRows
    return filteredRows.slice().sort((a, b) => compare(a[sortBy], b[sortBy], sortDir))
  }, [filteredRows, sortBy, sortDir])

  const guard = useMemo(() => validateClient(sql), [sql])
  const lineCount = useMemo(() => sql.split('\n').length, [sql])
  const statementCount = useMemo(() => maskSql(sql).semicolons.length, [sql])

  const apiOffline =
    views.error instanceof ApiError ||
    tables.error instanceof ApiError ||
    examples.error instanceof ApiError
      ? [views.error, tables.error, examples.error].find(
          (error) => error instanceof ApiError && error.isOffline,
        )
      : undefined
  const apiError =
    (views.error as Error | null) ?? (tables.error as Error | null) ?? (examples.error as Error | null)

  function syncScroll() {
    const area = editorRef.current
    if (!area) return
    if (highlightRef.current) {
      highlightRef.current.scrollTop = area.scrollTop
      highlightRef.current.scrollLeft = area.scrollLeft
    }
    if (gutterRef.current) gutterRef.current.scrollTop = area.scrollTop
  }

  function execute() {
    if (!guard.ok || run.isPending) return
    setResultFilter('')
    run.mutate()
  }

  // The shortcut lives on the editor card so it works from the textarea, the limit
  // selector and the run button without hijacking keys elsewhere on the page.
  function onEditorKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
      event.preventDefault()
      if (event.shiftKey) explain() // Ctrl+Shift+Enter runs EXPLAIN
      else execute()
    }
  }

  function onSort(key: string) {
    if (sortBy === key) {
      setSortDir((current) => (current === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortBy(key)
      setSortDir('asc')
    }
  }

  function loadExample(example: { sql?: unknown }) {
    setSql(String(example?.sql ?? ''))
    setSortBy(undefined)
    setResultFilter('')
    run.reset()
    editorRef.current?.focus()
  }

  function insertAtCursor(text: string) {
    const area = editorRef.current
    if (!area) {
      setSql((current) => (current.endsWith('\n') || !current ? `${current}${text}` : `${current} ${text}`))
      return
    }
    const start = area.selectionStart ?? sql.length
    const end = area.selectionEnd ?? sql.length
    const next = `${sql.slice(0, start)}${text}${sql.slice(end)}`
    setSql(next)
    requestAnimationFrame(() => {
      area.focus()
      const caret = start + text.length
      area.setSelectionRange(caret, caret)
      syncScroll()
    })
  }

  function reference(name: string) {
    // Insert the view/table identifier where the cursor is so it can be
    // queried immediately; the guard tolerates trailing "-- reference" notes.
    insertAtCursor(name)
  }

  function explain() {
    // Already an EXPLAIN plan request -> just run it. Otherwise prepend EXPLAIN
    // and run the new text directly (setState is async, so the mutation takes
    // the computed statement instead of reading the stale closure).
    const leading = maskSql(sql).masked.trimStart().replace(/^\(+/, '').trimStart()
    if (/^explain\b/i.test(leading) && validateClient(sql).ok) {
      execute()
      return
    }
    const next = `EXPLAIN ${sql.trim().replace(/^EXPLAIN\s+/i, '')}`
    setSql(next)
    if (!validateClient(next).ok || run.isPending) return
    setResultFilter('')
    run.mutate(next)
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

  function copySql() {
    void navigator.clipboard?.writeText(sql).catch(() => {})
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

  function loadHistorySql(nextSql: string) {
    setSql(nextSql)
    setSortBy(undefined)
    setResultFilter('')
    run.reset()
    editorRef.current?.focus()
  }

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
                <span className="flex items-center gap-1.5">
                  {apiOffline ? (
                    <Badge tone="danger">offline</Badge>
                  ) : apiError ? (
                    <Badge tone="warning">degraded</Badge>
                  ) : views.data ? (
                    <Badge tone="success">api up</Badge>
                  ) : (
                    <Badge tone="neutral">connecting</Badge>
                  )}
                  <kbd className="rounded border border-line bg-surface-3 px-1.5 py-0.5 font-mono text-[10px] text-subtle">
                    Ctrl/Cmd + Enter
                  </kbd>
                </span>
              }
            />
            {apiOffline ? (
              <div role="alert" className="mb-3 rounded-lg border border-danger/40 bg-danger-soft p-3">
                <p className="flex items-center gap-1.5 text-sm font-semibold text-danger">
                  <WifiOff className="h-4 w-4" /> API unreachable ({API_BASE})
                </p>
                <p className="mt-1 text-xs text-ink">
                  The editor, starter queries and schema browser all need the FastAPI server. Start it with{' '}
                  <code className="font-mono">./run-local.sh</code> or{' '}
                  <code className="font-mono">docker compose up api</code>, then confirm{' '}
                  <code className="font-mono">http://127.0.0.1:8000/api/v1/health</code> answers 200. The Vite dev
                  server proxies <code className="font-mono">/api</code> to{' '}
                  <code className="font-mono">VITE_PROXY_TARGET</code>.
                </p>
                <div className="mt-2 flex gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    icon={<Wifi className="h-3.5 w-3.5" />}
                    onClick={() => {
                      void queryClient.invalidateQueries({ queryKey: ['query-views'] })
                      void queryClient.invalidateQueries({ queryKey: ['query-tables'] })
                      void queryClient.invalidateQueries({ queryKey: ['query-examples'] })
                    }}
                  >
                    Retry connection
                  </Button>
                </div>
              </div>
            ) : null}

            <div className="sql-editor" data-testid="sql-editor">
              <div ref={gutterRef} className="sql-gutter" aria-hidden>
                {Array.from({ length: lineCount }).map((_, index) => (
                  <div key={index} className="sql-gutter-line">
                    {index + 1}
                  </div>
                ))}
              </div>
              <div className="sql-body">
                <pre ref={highlightRef} className="sql-highlight" aria-hidden>
                  <code dangerouslySetInnerHTML={{ __html: highlightSql(sql || ' ') }} />
                </pre>
                <textarea
                  ref={editorRef}
                  value={sql}
                  onChange={(event) => {
                    setSql(event.target.value)
                    setSortBy(undefined)
                  }}
                  onScroll={syncScroll}
                  onKeyDown={(event) => {
                    if (event.key === 'Tab') {
                      event.preventDefault()
                      const area = event.currentTarget
                      const start = area.selectionStart ?? 0
                      const end = area.selectionEnd ?? 0
                      setSql(`${sql.slice(0, start)}  ${sql.slice(end)}`)
                      requestAnimationFrame(() => area.setSelectionRange(start + 2, start + 2))
                    }
                  }}
                  rows={10}
                  spellCheck={false}
                  autoCapitalize="off"
                  autoCorrect="off"
                  aria-label="SQL statement"
                  placeholder="SELECT ... FROM vw_price_history ..."
                  className="sql-textarea"
                />
              </div>
            </div>

            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Badge tone={guard.ok ? 'success' : 'danger'}>
                {guard.ok ? 'read-only ✓' : `rejected: ${guard.reason}`}
              </Badge>
              <Badge tone="neutral">
                {lineCount} line{lineCount === 1 ? '' : 's'}
              </Badge>
              {statementCount > 1 ? <Badge tone="warning">{statementCount} statements</Badge> : null}
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Button
                variant="primary"
                size="sm"
                loading={run.isPending}
                disabled={!guard.ok}
                icon={<Play className="h-4 w-4" />}
                onClick={execute}
                title={guard.ok ? 'Run (Ctrl/Cmd+Enter)' : guard.reason}
              >
                Run query
              </Button>
              <Button
                variant="secondary"
                size="sm"
                icon={<ScrollText className="h-4 w-4" />}
                onClick={explain}
                title="Wrap in EXPLAIN (Ctrl/Cmd+Shift+Enter)"
              >
                Explain
              </Button>
              <Button variant="secondary" size="sm" icon={<Wand2 className="h-4 w-4" />} onClick={() => setSql(formatSql)}>
                Format
              </Button>
              <Button variant="ghost" size="sm" icon={<Copy className="h-4 w-4" />} onClick={copySql} title="Copy SQL">
                Copy
              </Button>
              <Button
                variant="ghost"
                size="sm"
                icon={<Eraser className="h-4 w-4" />}
                onClick={() => {
                  setSql('')
                  run.reset()
                  editorRef.current?.focus()
                }}
              >
                Clear
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
            <p className="mt-2 text-[11px] text-subtle">
              Ctrl/Cmd+Enter runs · Ctrl/Cmd+Shift+Enter explains · Tab indents · one statement, {formatNumber(limit)}{' '}
              rows max, capped inside the database.
            </p>
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
              {examples.data.map((example: { title: string; sql: string }) => (
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
            <EmptyState kind="file" title="No starter query available" />
          )}
        </Card>

        <Card>
          <CardHeader
            title="Analytical views"
            subtitle="Click a view to insert it at the cursor"
            icon={<Table2 className="h-4 w-4" />}
          />
          {views.isError ? (
            <ErrorState message={(views.error as Error)?.message} onRetry={() => views.refetch()} />
          ) : views.isLoading && !views.data ? (
            <LoadingState label={'Loading views…'} rows={2} />
          ) : views.data?.length ? (
            <div className="flex max-h-48 flex-wrap gap-1.5 overflow-auto">
              {views.data.map((view: { name: string }) => (
                <button
                  key={view.name}
                  onClick={() => reference(String(view.name))}
                  title={`Insert ${view.name} at cursor`}
                  className="rounded-full border border-line bg-surface px-2.5 py-1 font-mono text-[11px] text-muted hover:border-line-strong hover:text-ink"
                >
                  {view.name}
                </button>
              ))}
            </div>
          ) : (
            <EmptyState kind="database" title="No analytical view found" message="The warehouse exposes no view yet." />
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
                        title={`Insert ${name} at cursor`}
                        className="rounded-md border border-line bg-surface px-2 py-1 font-mono text-[11px] text-muted hover:border-line-strong hover:text-ink"
                      >
                        {name}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
              <p className="border-t border-line pt-2 text-[11px] leading-relaxed text-subtle">
                The console runs on a read-only connection: no DDL, no DML and one statement per query. Secret tables
                ({FORBIDDEN_TABLES.join(', ')}) are never readable here.
              </p>
            </div>
          ) : (
            <EmptyState kind="database" title="No schema published" message="The API returned no table group." />
          )}
        </Card>

        <QueryHistoryPanel onLoad={loadHistorySql} />
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
                <Badge tone="success">
                  <CheckCircle2 className="h-3 w-3" /> complete
                </Badge>
              )}
              <span className="ml-auto w-full sm:w-56">
                <SearchInput value={resultFilter} onChange={setResultFilter} placeholder="Filter rows…" />
              </span>
            </div>
          ) : null}
        </div>

        {run.isError ? (
          <div className="space-y-2 p-4">
            <QueryError error={run.error} onRetry={execute} apiBase={API_BASE} />
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="secondary" icon={<Play className="h-4 w-4" />} onClick={execute}>
                Run again
              </Button>
              <Button size="sm" variant="ghost" icon={<X className="h-4 w-4" />} onClick={() => run.reset()}>
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
            kind="search"
            title="The statement returned no row"
            message="The SQL was accepted but matched nothing. Check the WHERE clause or widen the date window."
          />
        ) : !sortedRows.length ? (
          <EmptyState
            kind="search"
            title="No row matches the filter"
            message={`"${resultFilter}" hides all ${formatNumber(rows.length)} returned rows. Clear the filter to see them.`}
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
function QueryError({
  error,
  onRetry,
  apiBase,
}: {
  error: Error | null
  onRetry: () => void
  apiBase: string
}) {
  if (error instanceof ApiError) {
    if (error.isOffline) {
      return (
        <div role="alert" className="rounded-lg border border-danger/40 bg-danger-soft p-3">
          <p className="text-sm font-semibold text-danger">The query failed (HTTP 0) — API unreachable</p>
          <p className="mt-1 text-xs text-ink">Cannot reach the API. Is the server running?</p>
          <ol className="mt-2 list-decimal space-y-1 pl-5 text-[11px] text-muted">
            <li>
              Start the stack: <code className="font-mono">./run-local.sh</code> (or{' '}
              <code className="font-mono">docker compose up -d api postgres</code>).
            </li>
            <li>
              Confirm <code className="font-mono">GET {apiBase.replace(/\/v1$/, '')}/health</code> returns 200.
            </li>
            <li>
              In dev, the Vite proxy forwards <code className="font-mono">/api</code> to{' '}
              <code className="font-mono">VITE_PROXY_TARGET</code> (default{' '}
              <code className="font-mono">http://127.0.0.1:8000</code>); in production nginx does the same.
            </li>
            <li>Sign in again — an expired session surfaces as 401, not as HTTP 0.</li>
          </ol>
          <div className="mt-2">
            <Button size="sm" variant="secondary" icon={<Play className="h-4 w-4" />} onClick={onRetry}>
              Retry once the API is up
            </Button>
          </div>
        </div>
      )
    }
    const details = error.details as { errors?: { message?: string }[]; hint?: string } | undefined
    const reasons = (details?.errors ?? [])
      .map((item) => item.message)
      .filter(Boolean)
      .join(' ')
    if (error.status === 422) {
      return (
        <div role="alert" className="rounded-lg border border-danger/40 bg-danger-soft p-3">
          <p className="text-sm font-semibold text-danger">Statement rejected by the read-only guard</p>
          <p className="mt-1 text-xs text-ink">{reasons || error.message}</p>
          {details?.hint ? <p className="mt-1 text-[11px] text-muted">{details.hint}</p> : null}
          <p className="mt-1 text-[11px] text-muted">
            A single SELECT, WITH or EXPLAIN statement is accepted; writes, DDL and semicolon-separated batches are
            refused.
          </p>
        </div>
      )
    }
    if (error.status === 403) {
      return (
        <div role="alert" className="rounded-lg border border-danger/40 bg-danger-soft p-3">
          <p className="text-sm font-semibold text-danger">Forbidden (HTTP 403)</p>
          <p className="mt-1 text-xs text-ink">{error.message}</p>
          <p className="mt-1 text-[11px] text-muted">
            The <code className="font-mono">query</code> right is required. Sign in with a viewer, analyst or admin
            account, or ask an admin to grant it.
          </p>
        </div>
      )
    }
    return (
      <div role="alert" className="rounded-lg border border-danger/40 bg-danger-soft p-3">
        <p className="text-sm font-semibold text-danger">The query failed (HTTP {error.status})</p>
        <p className="mt-1 text-xs text-ink">{error.message}</p>
        <p className="mt-1 text-[11px] text-muted">
          Error code <span className="font-mono">{error.code}</span> - check the table and column names against the
          schema browser.
        </p>
      </div>
    )
  }
  return <ErrorState title="The query could not be sent" message={error?.message ?? 'Unknown error'} />
}
