/**
 * ExportButton: download any registered dataset as CSV or JSON.
 *
 * The dataset list, its supported filters and the row cap all come from
 * `GET /export/datasets`, so this control never drifts from what the API can serve.
 */

import type React from 'react'
import { useState } from 'react'
import { Check, Download, FileJson, Sheet } from 'lucide-react'

import { Button, type ButtonProps } from '@/components/ui'
import { downloadExport, endpoints, type QueryValue } from '@/lib/api'
import { useApiQuery } from '@/hooks/useApi'

type ButtonProps = React.ComponentProps<typeof Button>

type Props = Omit<ButtonProps, 'onClick' | 'loading' | 'children'> & {
  dataset: string
  /** Filters forwarded to the export so the file matches what the user is looking at. */
  params?: Record<string, QueryValue>
  limit?: number
  label?: string
}

export function ExportButton({ dataset, params, limit = 5000, label, variant = 'secondary', ...rest }: Props) {
  const [busy, setBusy] = useState<'csv' | 'json' | null>(null)
  const [done, setDone] = useState<'csv' | 'json' | null>(null)
  const catalogue = useApiQuery(['export-datasets'], endpoints.exportDatasets)

  const info = (catalogue.data?.datasets ?? []).find((item: any) => item.key === dataset)

  async function run(format: 'csv' | 'json') {
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