/**
 * Query-lab history and snippets.
 *
 * Every execution is recorded server-side (`GET /queries/history`); a run can
 * be pinned as a named snippet, reloaded into the editor, or deleted. Unsaved
 * runs are pruned by the API past a keep window, snippets never are.
 */

import { useState } from 'react'
import { Bookmark, BookmarkPlus, History, Play, Trash2 } from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { Badge, Button, Card, CardHeader, EmptyState, ErrorState, LoadingState, TextInput, useToast } from './ui'
import { endpoints } from '@/lib/api'
import { useApiQuery } from '@/hooks/useApi'
import { formatDuration, formatRelative, truncate } from '@/lib/format'
import { cn } from '@/lib/cn'

export default function QueryHistoryPanel({ onLoad }: { onLoad: (sql: string) => void }) {
  const toast = useToast()
  const queryClient = useQueryClient()
  const [filter, setFilter] = useState<'all' | 'snippets'>('all')
  const [naming, setNaming] = useState<number | null>(null)
  const [name, setName] = useState('')

  const history = useApiQuery(['query-history'], () => endpoints.queryHistory({ limit: 100 }), {
    staleTime: 15_000,
  })

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ['query-history'] })

  const saveSnippet = useMutation({
    mutationFn: ({ id, snippetName }: { id: number; snippetName: string }) =>
      endpoints.saveQuerySnippet(id, snippetName),
    onSuccess: () => {
      setNaming(null)
      setName('')
      invalidate()
      toast.success('Snippet saved', 'It is pinned and survives history pruning.')
    },
    onError: (error: Error) => toast.error('Could not save the snippet', error.message),
  })

  const remove = useMutation({
    mutationFn: (id: number) => endpoints.deleteQueryHistory(id),
    onSuccess: () => {
      invalidate()
      toast.success('Entry deleted')
    },
    onError: (error: Error) => toast.error('Could not delete the entry', error.message),
  })

  const clear = useMutation({
    mutationFn: () => endpoints.clearQueryHistory(),
    onSuccess: (payload: any) => {
      invalidate()
      toast.success('History cleared', payload?.message ?? 'Snippets were kept.')
    },
    onError: (error: Error) => toast.error('Could not clear history', error.message),
  })

  const entries: any[] = history.data ?? []
  const visible = filter === 'snippets' ? entries.filter((entry) => entry.is_saved) : entries

  return (
    <Card>
      <CardHeader
        title="History & snippets"
        subtitle="Every run is recorded; pin the keepers"
        icon={<History className="h-4 w-4" />}
        action={
          <div className="flex items-center gap-1.5">
            <div className="inline-flex rounded-lg border border-line bg-surface-3 p-0.5" role="group" aria-label="History filter">
              {(['all', 'snippets'] as const).map((option) => (
                <button
                  key={option}
                  onClick={() => setFilter(option)}
                  aria-pressed={filter === option}
                  className={cn(
                    'rounded-md px-2 py-0.5 text-xs font-medium text-muted hover:text-ink',
                    filter === option && 'bg-surface text-ink shadow-sm',
                  )}
                >
                  {option === 'all' ? 'All' : 'Snippets'}
                </button>
              ))}
            </div>
            <Button
              size="sm"
              variant="ghost"
              icon={<Trash2 className="h-3.5 w-3.5" />}
              disabled={!entries.some((entry) => !entry.is_saved)}
              onClick={() => clear.mutate()}
            >
              Clear
            </Button>
          </div>
        }
      />
      {history.isError ? (
        <ErrorState message={(history.error as Error)?.message} onRetry={() => history.refetch()} />
      ) : history.isLoading && !history.data ? (
        <LoadingState label="Loading history…" rows={3} />
      ) : !visible.length ? (
        <EmptyState
          kind="file"
          title={filter === 'snippets' ? 'No snippets yet' : 'No runs recorded'}
          message={
            filter === 'snippets'
              ? 'Pin a run with the bookmark button to keep it forever.'
              : 'Run a statement and it appears here automatically.'
          }
        />
      ) : (
        <ul className="max-h-96 space-y-1.5 overflow-auto pr-0.5">
          {visible.map((entry) => (
            <li
              key={entry.history_id}
              className="rounded-lg border border-line bg-surface-2 px-2.5 py-2 hover:border-line-strong"
            >
              <div className="flex items-start gap-2">
                <button
                  onClick={() => onLoad(entry.sql)}
                  title="Load into the editor"
                  className="min-w-0 flex-1 text-left"
                >
                  <span className="block truncate font-mono text-[11px] text-ink">
                    {entry.name ?? truncate(entry.sql.replace(/\s+/g, ' '), 72)}
                  </span>
                  <span className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[10px] text-subtle">
                    <span>{formatRelative(entry.created_at)}</span>
                    <span className="tabular-nums">{entry.row_count} rows</span>
                    <span className="tabular-nums">{formatDuration(entry.duration_ms)}</span>
                    {entry.truncated ? <span>truncated</span> : null}
                  </span>
                </button>
                <span className="flex shrink-0 items-center gap-0.5">
                  {entry.is_saved ? (
                    <Badge tone="brand">
                      <Bookmark className="h-3 w-3" aria-hidden />
                    </Badge>
                  ) : (
                    <button
                      onClick={() => {
                        setNaming(entry.history_id)
                        setName('')
                      }}
                      aria-label="Pin as snippet"
                      title="Pin as a named snippet"
                      className="rounded-md p-1.5 text-subtle hover:bg-surface-3 hover:text-ink"
                    >
                      <BookmarkPlus className="h-3.5 w-3.5" />
                    </button>
                  )}
                  <button
                    onClick={() => onLoad(entry.sql)}
                    aria-label="Load into editor"
                    title="Load into the editor"
                    className="rounded-md p-1.5 text-subtle hover:bg-surface-3 hover:text-ink"
                  >
                    <Play className="h-3.5 w-3.5" />
                  </button>
                  <button
                    onClick={() => remove.mutate(entry.history_id)}
                    aria-label="Delete entry"
                    title="Delete this entry"
                    className="rounded-md p-1.5 text-subtle hover:bg-surface-3 hover:text-danger"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </span>
              </div>
              {naming === entry.history_id ? (
                <div className="mt-2 flex gap-1.5">
                  <TextInput
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    placeholder="Snippet name…"
                    aria-label="Snippet name"
                    autoFocus
                    className="h-8 py-0 text-xs"
                  />
                  <Button
                    size="sm"
                    variant="primary"
                    loading={saveSnippet.isPending}
                    disabled={!name.trim()}
                    onClick={() => saveSnippet.mutate({ id: entry.history_id, snippetName: name.trim() })}
                  >
                    Pin
                  </Button>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
