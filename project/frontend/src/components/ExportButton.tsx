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

  const info = (catalogue.data?.datasets ?? []).find((item: any) => item.key === dataset)

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

  return (
    <div className="flex items-center gap-1.5">
      <Button
        {...rest}
        variant={variant}
        loading={busy === 'csv'}
        icon={done === 'csv' ? <Check className="h-4 w-4" /> : <Sheet className="h-4 w-4" />}
        title={
          info
            ? `Download ${info.title} as CSV${info.filters.length ? ` · filters: ${info.filters.join(', ')}` : ''}`
            : `Download ${dataset} as CSV`
        }
        onClick={() => void run('csv')}
      >
        {label ?? 'CSV'}
      </Button>
      <Button
        {...rest}
        variant="ghost"
        loading={busy === 'xlsx'}
        icon={done === 'xlsx' ? <Check className="h-4 w-4" /> : <FileSpreadsheet className="h-4 w-4" />}
        title={`Download ${dataset} as Excel`}
        onClick={() => void run('xlsx')}
      >
        Excel
      </Button>
      <Button
        {...rest}
        variant="ghost"
        loading={busy === 'json'}
        icon={done === 'json' ? <Check className="h-4 w-4" /> : <FileJson className="h-4 w-4" />}
        title={`Download ${dataset} as JSON`}
        onClick={() => void run('json')}
      >
        JSON
      </Button>
    </div>
  )
}

export default ExportButton