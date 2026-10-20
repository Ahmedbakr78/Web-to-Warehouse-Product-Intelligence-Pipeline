/**
 * ExportButton: download any registered dataset as CSV, Excel or JSON.
 *
 * The dataset list, its supported filters and the row cap all come from
 * `GET /export/datasets`, so this control never drifts from what the API can serve.
 */

import type React from 'react'
import { useState } from 'react'
import { Check, FileJson, FileSpreadsheet, Sheet } from 'lucide-react'

import { Button } from '@/components/ui'
import { downloadExport, endpoints, type QueryValue } from '@/lib/api'
import { useApiQuery } from '@/hooks/useApi'
import { useProfilePreferences } from '@/hooks/usePreferences'

type ButtonProps = React.ComponentProps<typeof Button>

type ExportFormat = 'csv' | 'xlsx' | 'json'

type Props = Omit<ButtonProps, 'onClick' | 'loading' | 'children'> & {
  dataset: string
  /** Filters forwarded to the export so the file matches what the user is looking at. */
  params?: Record<string, QueryValue>
  limit?: number
  label?: string
}

export function ExportButton({ dataset, params, limit = 5000, label, variant = 'secondary', ...rest }: Props) {
  const [busy, setBusy] = useState<ExportFormat | null>(null)
  const [done, setDone] = useState<ExportFormat | null>(null)
  const catalogue = useApiQuery(['export-datasets'], endpoints.exportDatasets)
  const { defaultExportFormat } = useProfilePreferences()

  const info = (catalogue.data?.datasets ?? []).find((item: any) => item.key === dataset)
  // The account screen picks which format is offered first; the others stay
  // available so a one-off download never needs a detour through settings.
  const preferred: ExportFormat = defaultExportFormat === 'xlsx' ? 'xlsx' : defaultExportFormat === 'json' ? 'json' : 'csv'
  const order: ExportFormat[] = [preferred, ...(['csv', 'xlsx', 'json'] as ExportFormat[]).filter((item) => item !== preferred)]

  async function run(format: ExportFormat) {
    setBusy(format)
    try {
      await downloadExport(dataset, format, params ?? {}, limit)
      setDone(format)
      window.setTimeout(() => setDone(null), 2000)
    } finally {
      setBusy(null)
    }
  }

  const icons: Record<ExportFormat, React.ReactNode> = {
    csv: <Sheet className="h-4 w-4" />,
    xlsx: <FileSpreadsheet className="h-4 w-4" />,
    json: <FileJson className="h-4 w-4" />,
  }
  const labels: Record<ExportFormat, string> = { csv: 'CSV', xlsx: 'Excel', json: 'JSON' }
  const titles: Record<ExportFormat, string> = {
    csv: `Download ${dataset} as CSV`,
    xlsx: `Download ${dataset} as Excel`,
    json: `Download ${dataset} as JSON`,
  }

  return (
    <div className="flex items-center gap-1.5">
      {order.map((format, index) => (
        <Button
          key={format}
          {...rest}
          variant={index === 0 ? variant : 'ghost'}
          loading={busy === format}
          icon={done === format ? <Check className="h-4 w-4" /> : icons[format]}
          title={
            format === 'csv' && info
              ? `Download ${info.title} as CSV${info.filters.length ? ` · filters: ${info.filters.join(', ')}` : ''}`
              : titles[format]
          }
          onClick={() => void run(format)}
        >
          {index === 0 && label ? label : labels[format]}
        </Button>
      ))}
    </div>
  )
}

export default ExportButton