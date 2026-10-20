/**
 * Forecast chart: history, the projected line, and a shaded prediction interval.
 *
 * Recharts' `Area` cannot draw only a band (between two series) without a stacked
 * trick, so the interval is drawn as two stacked areas: an invisible "floor" down to
 * the lower bound and a translucent band up to the upper bound. Chart animation is off
 * everywhere in this app, so a reload never animates the projection into place.
 */

import { useMemo } from 'react'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { formatCompact, formatPrice } from '@/lib/format'

const GRID = 'var(--chart-grid)'
const TEXT = 'var(--text-subtle)'

export type ForecastPoint = {
  date: string
  value: number
  lower: number
  upper: number
}

export function ForecastChart({
  history,
  forecast,
  height = 300,
  currency = 'USD',
  forecastLabel = 'Forecast',
}: {
  /** Observed daily prices, oldest first. */
  history: Array<{ date: string; value: number | null }>
  /** Projected points with their interval bounds. */
  forecast: ForecastPoint[]
  height?: number
  currency?: string
  forecastLabel?: string
}) {
  const data = useMemo(() => {
    const rows: Array<Record<string, number | string | null>> = []

    for (const point of history) {
      rows.push({ date: point.date, observed: point.value, floor: null, band: null, forecast: null })
    }

    const firstForecastDate = forecast[0]?.date
    // Anchor the band on the last observed point so the two lines meet rather than
    // starting the projection in mid-air.
    const lastObserved = history.filter((point) => point.value !== null).at(-1)
    if (lastObserved && firstForecastDate) {
      rows.push({
        date: lastObserved.date,
        observed: lastObserved.value,
        floor: lastObserved.value,
        band: 0,
        forecast: lastObserved.value,
      })
    }

    for (const point of forecast) {
      rows.push({
        date: point.date,
        observed: null,
        floor: point.lower,
        band: Math.max(0, point.upper - point.lower),
        forecast: point.value,
      })
    }
    return rows
  }, [history, forecast])

  if (!data.length) return null

  const boundary = firstForecastIndex(history, forecast)

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="forecast-band" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--brand-500)" stopOpacity={0.28} />
            <stop offset="100%" stopColor="var(--brand-500)" stopOpacity={0.06} />
          </linearGradient>
        </defs>

        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={GRID} />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 11, fill: TEXT }}
          tickLine={false}
          axisLine={{ stroke: GRID }}
          minTickGap={28}
        />
        <YAxis
          tick={{ fontSize: 11, fill: TEXT }}
          tickLine={false}
          axisLine={false}
          width={56}
          tickFormatter={(value: number) => formatCompact(value)}
        />
        <Tooltip
          contentStyle={{
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 10,
            fontSize: 12,
          }}
          labelStyle={{ color: 'var(--text)', fontWeight: 600 }}
          formatter={(value: number, name: string) => {
            if (name === 'observed') return [formatPrice(value, currency), 'Observed']
            if (name === 'forecast') return [formatPrice(value, currency), forecastLabel]
            return [value, name]
          }}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} />

        {/* Invisible floor down to the lower bound, then the visible band. */}
        <Area
          dataKey="floor"
          stackId="interval"
          stroke="none"
          fill="none"
          isAnimationActive={false}
          legendType="none"
          name="lower"
        />
        <Area
          dataKey="band"
          stackId="interval"
          stroke="none"
          fill="url(#forecast-band)"
          isAnimationActive={false}
          legendType="none"
          name="interval"
        />

        <Area
          dataKey="observed"
          stroke="var(--chart-1)"
          strokeWidth={2}
          fill="var(--chart-1)"
          fillOpacity={0.08}
          isAnimationActive={false}
          name="observed"
          connectNulls
        />
        <Line
          dataKey="forecast"
          stroke="var(--brand-500)"
          strokeWidth={2}
          strokeDasharray="5 4"
          dot={false}
          isAnimationActive={false}
          name={forecastLabel}
          connectNulls
        />

        {boundary ? (
          <ReferenceLine
            x={boundary}
            stroke="var(--text-subtle)"
            strokeDasharray="3 3"
            label={{ value: 'now', position: 'insideTopRight', fontSize: 10, fill: TEXT }}
          />
        ) : null}
      </ComposedChart>
    </ResponsiveContainer>
  )
}

function firstForecastIndex(
  history: Array<{ date: string; value: number | null }>,
  forecast: ForecastPoint[],
): string | null {
  const first = forecast[0]?.date
  if (!first) return null
  return history.some((point) => point.date === first) ? null : first
}