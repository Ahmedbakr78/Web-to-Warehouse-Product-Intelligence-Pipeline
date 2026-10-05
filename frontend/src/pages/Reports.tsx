/**
 * Report builder.
 *
 * The API returns a report as a list of typed blocks, and this screen renders those
 * blocks with the same components used everywhere else, so what is reviewed on screen
 * is the report - not a preview of it. The HTML, JSON and PDF paths are all generated
 * from that one payload on the server, so no block can drift between formats.
 */

import { useMemo, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import {
  CalendarRange,
  CircleAlert,
  Download,
  FileText,
  Info,
  Printer,
  Table2,
  TrendingUp,
} from 'lucide-react'

import {
  Badge,
  Button,
  Card,
  CardHeader,
  DataTable,
  LoadingState,
  Select,
  StatTile,
  useToast,
} from '@/components/ui'
import { BarSeries } from '@/components/charts'
import { API_BASE, downloadBinary, endpoints, tokenStore } from '@/lib/api'
import { useApiQuery } from '@/hooks/useApi'
import { formatDateTime, formatNumber } from '@/lib/format'
import { cn } from '@/lib/cn'

type Block = Record<string, any>

const WINDOWS = [
  { id: 7, label: 'Last 7 days' },
  { id: 30, label: 'Last 30 days' },
  { id: 90, label: 'Last 90 days' },
  { id: 365, label: 'Last 12 months' },
]

function BlockTable({ block }: { block: Block }) {
  return (
    <DataTable
      rows={(block.rows ?? []) as any[]}
      rowKey={(_row, index) => String(index)}
      maxHeight={320}
      columns={(block.columns ?? []).map((column: Block) => ({
        key: column.key,
        header: column.label,
        align: column.align,
        render: (row: Block) => String(row[column.key] ?? '—'),
      }))}
    />
  )
}

function BlockRenderer({ block }: { block: Block }) {
  switch (block.type) {
    case 'heading':
      return (
        <h3 className="flex items-center gap-2 text-sm font-semibold text-ink">
          <Table2 className="h-3.5 w-3.5 text-brand-500" aria-hidden />
          {block.title}
        </h3>
      )
    case 'tiles':
      return (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {(block.tiles ?? []).map((tile: Block) => (
            <StatTile key={tile.label} label={tile.label} value={tile.value} hint={tile.hint} />
          ))}
        </div>
      )
    case 'callout':
      return (
        <div className="flex items-start gap-2 rounded-xl border border-line bg-surface-2 p-3 text-xs leading-relaxed text-muted">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-brand-500" aria-hidden />
          <div>
            {block.title ? <p className="font-medium text-ink">{block.title}</p> : null}
            <p>{block.body}</p>
          </div>
        </div>
      )
    case 'table':
      return <BlockTable block={block} />
    case 'bars':
      return (
        <BarSeries
          data={((block.items ?? []) as any[]).map((item: Block) => ({ label: String(item.label), value: Number(item.value) }))}
          xKey="label"
          bars={[{ key: 'value', label: block.title ?? 'value' }]}
          height={220}
        />
      )
    case 'text':
      return <p className="text-xs leading-relaxed text-muted">{block.body ?? block.text}</p>
    default:
      // An unknown block type is skipped rather than crashing the report: a newer
      // server can add block types without breaking an older cached frontend.
      return null
  }
}

export default function Reports() {
  const toast = useToast()
  const [template, setTemplate] = useState('executive_summary')
  const [days, setDays] = useState(30)
  const [sections, setSections] = useState<string[]>([])

  const templates = useApiQuery(['report-templates'], endpoints.reportTemplates, { staleTime: 600_000 })
  const current = (templates.data?.templates ?? []).find((item: any) => item.key === template)
  const report = useApiQuery(
    ['report', template, days],
    () => endpoints.reportData(template, { days, sections: sections.length ? sections.join(',') : undefined }),
    { enabled: Boolean(template) },
  )

  const pdf = useMutation({
    mutationFn: () =>
      downloadBinary(
        `/reports/${template}/pdf`,
        { days, sections: sections.length ? sections.join(',') : undefined },
        `${template}-report.pdf`,
      ),
    onSuccess: () => toast.success('PDF downloaded'),
    onError: (error) => toast.error('Could not render that PDF', (error as Error).message),
  })

  const csv = useMutation({
    mutationFn: async () => {
      // Every table block becomes one CSV section, so the export mirrors the screen
      // instead of being a separate, second definition of what the report is.
      const tables = (report.data?.blocks ?? []).filter((block: Block) => block.type === 'table')
      if (!tables.length) throw new Error('This report has no table to export')
      const parts = tables.map((block: Block) => {
        const header = block.columns.map((column: Block) => column.label).join(',')
        const body = block.rows
          .map((row: Block) =>
            block.columns
              .map((column: Block) => {
                const value = String(row[column.key] ?? '')
                return /[",\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value
              })
              .join(','),
          )
          .join('\n')
        return `${block.title ?? 'table'}\n${header}\n${body}`
      })
      const blob = new Blob([parts.join('\n\n')], { type: 'text/csv;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `${template}-${days}d.csv`
      anchor.click()
      URL.revokeObjectURL(url)
    },
    onSuccess: () => toast.success('CSV downloaded'),
    onError: (error) => toast.error('Could not export that CSV', (error as Error).message),
  })

  const openHtml = () => {
    // A new tab, with the token in the query string: `window.open` cannot send a header
    // and the API does not accept the token from `localStorage`.
    const params = new URLSearchParams({ days: String(days) })
    const token = tokenStore.get()
    if (token) params.set('token', token ?? '')
    if (sections.length) params.set('sections', sections.join(','))
    window.open(`${API_BASE}/reports/${template}?${params.toString()}`, '_blank', 'noopener')
  }

  const blocks = useMemo(() => (report.data?.blocks ?? []) as Block[], [report.data])
  const blockCount = blocks.length
  const tableCount = blocks.filter((block) => block.type === 'table').length

  const summary = useMemo(
    () =>
      blocks
        .filter((block) => block.type === 'tiles')
        .flatMap((block) => (block.tiles ?? []) as Block[])
        .slice(0, 8),
    [blocks],
  )

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title="Report builder"
          subtitle="Every report is generated from the same blocks, so HTML, JSON, CSV and PDF always agree"
          icon={<FileText className="h-4 w-4" />}
        />
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <div>
            <p className="stat-label mb-1.5">Report</p>
            <Select
            value={template}
            onChange={(event) => {
              setTemplate(event.target.value)
              setSections([])
            }}
          >
            {(templates.data?.templates ?? []).map((item: any) => (
              <option key={item.key} value={item.key}>
                {item.title}
              </option>
            ))}
          </Select>
          </div>
          <div>
            <p className="stat-label mb-1.5">Window</p>
            <Select
              value={String(days)}
              onChange={(event) => setDays(Number(event.target.value))}
            >
              {WINDOWS.map((item) => (
                <option key={item.id} value={String(item.id)}>
                  {item.label}
                </option>
              ))}
            </Select>
          </div>
          <div className="flex items-end gap-2">
            <Button
              variant="primary"
              icon={<Printer className="h-4 w-4" />}
              loading={pdf.isPending}
              disabled={!templates.data?.pdf_available}
              onClick={() => pdf.mutate()}
            >
              PDF
            </Button>
            <Button variant="secondary" icon={<Download className="h-4 w-4" />} loading={csv.isPending} onClick={() => csv.mutate()}>
              CSV
            </Button>
            <Button variant="ghost" onClick={openHtml}>
              HTML
            </Button>
          </div>
        </div>

        {current?.subtitle ? <p className="mt-3 text-xs text-muted">{current.subtitle}</p> : null}

        {current?.sections?.length ? (
          <div className="mt-3">
            <p className="stat-label mb-1.5">Sections</p>
            <div className="flex flex-wrap gap-1.5">
              {(current.sections as string[]).map((section) => {
                const on = sections.length === 0 || sections.includes(section)
                return (
                  <button
                    key={section}
                    type="button"
                    onClick={() =>
                      setSections((current2) => {
                        const base = current2.length === 0 ? ((current?.sections as string[]) ?? []) : current2
                        return base.includes(section) ? base.filter((item) => item !== section) : [...base, section]
                      })
                    }
                    className={cn(
                      'rounded-lg border px-2.5 py-1 text-[11px] font-medium capitalize transition-colors',
                      on ? 'border-brand-500 bg-brand-500/10 text-brand-600' : 'border-line text-subtle hover:bg-surface-2',
                    )}
                  >
                    {section.replace(/_/g, ' ')}
                  </button>
                )
              })}
              {sections.length ? (
                <button type="button" onClick={() => setSections([])} className="px-1 text-[11px] text-subtle underline">
                  reset
                </button>
              ) : null}
            </div>
            <p className="mt-1.5 text-[11px] text-subtle">Nothing selected means every section is included.</p>
          </div>
        ) : null}

        {templates.data && !templates.data.pdf_available ? (
          <p className="mt-3 flex items-start gap-2 rounded-lg bg-warning-soft p-2.5 text-[11px] text-muted">
            <CircleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" aria-hidden />
            {templates.data.pdf_unavailable_reason || 'PDF rendering is unavailable in this deployment.'} HTML, JSON and
            CSV still work.
          </p>
        ) : null}
      </Card>

      {summary.length ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {summary.map((tile: Block) => (
            <StatTile key={tile.label} label={tile.label} value={tile.value} hint={tile.hint} />
          ))}
        </div>
      ) : null}

      <Card padded={false}>
        <div className="flex flex-wrap items-start justify-between gap-3 p-4 sm:p-5">
          <CardHeader
            title={report.data?.title ?? current?.title ?? 'Report'}
            subtitle={
              report.data
                ? `${blockCount} block(s), ${tableCount} table(s) · generated ${formatDateTime(report.data.generated_at)}`
                : 'Loading the blocks the server assembles for these filters'
            }
            icon={<TrendingUp className="h-4 w-4" />}
          />
          {report.data ? (
            <div className="flex items-center gap-2">
              <Badge tone="neutral">{days} day window</Badge>
              <Badge tone="neutral">
                {formatNumber((report.data.blocks ?? []).length)} blocks
              </Badge>
            </div>
          ) : null}
        </div>

        {report.isLoading ? (
          <div className="p-4">
            <LoadingState label="Assembling the report…" rows={4} />
          </div>
        ) : report.isError ? (
          <div className="p-6 text-center text-xs text-danger">
            {(report.error as Error)?.message ?? 'Could not build that report.'}
          </div>
        ) : (
          <div className="space-y-5 p-4 sm:p-5">
            {blocks.map((block, index) => (
              <BlockRenderer key={`${block.type}-${index}`} block={block} />
            ))}
            {!blocks.length ? <p className="text-center text-xs text-subtle">This report has no blocks.</p> : null}
          </div>
        )}
      </Card>

      <Card>
        <CardHeader
          title="How a report is assembled"
          subtitle="One definition, four formats"
          icon={<CalendarRange className="h-4 w-4" />}
        />
        <ol className="grid gap-3 text-xs text-muted sm:grid-cols-2 lg:grid-cols-4">
          {[
            { title: '1. Query', body: 'The template runs against the 20 analytical views, never the raw tables.' },
            { title: '2. Assemble', body: 'Results become typed blocks: heading, tiles, table, bars, callout.' },
            { title: '3. Render', body: 'The screen, the HTML preview, the CSV and the PDF consume those same blocks.' },
            { title: '4. Export', body: 'A large PDF is queued as a job so WeasyPrint never blocks a request.' },
          ].map((step) => (
            <li key={step.title} className="rounded-xl border border-line bg-surface-2 p-3">
              <p className="font-medium text-ink">{step.title}</p>
              <p className="mt-1 leading-relaxed">{step.body}</p>
            </li>
          ))}
        </ol>
      </Card>
    </div>
  )
}