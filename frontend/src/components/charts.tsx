/**
 * Chart components built on Recharts.
 *
 * All colours come from CSS variables so charts follow the light/dark theme
 * automatically, and tooltips are custom-built (Recharts' default tooltip is
 * disabled in the stylesheet) to match the design system.
 */

import { type ReactNode, useMemo } from 'react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { cn } from '@/lib/cn'
import { formatCompact, formatNumber } from '@/lib/format'

const AXIS_STYLE = { fontSize: 11, fill: 'var(--text-subtle)' }
const GRID_COLOR = 'var(--chart-grid)'
const SERIES = ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)', 'var(--chart-5)', 'var(--chart-6)']

type TooltipEntry = { name?: string; value?: number | string; color?: string; dataKey?: string | number }

function ChartTooltip({
  active,
  payload,
  label,
  formatter,
  labelFormatter,
}: {
  active?: boolean
  payload?: TooltipEntry[]
  label?: string | number
  formatter?: (value: number, name: string) => string
  labelFormatter?: (label: string | number) => string
}) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 shadow-pop">
      <p className="mb-1 text-[11px] font-semibold text-ink">{labelFormatter ? labelFormatter(label ?? '') : label}</p>
      <ul className="space-y-0.5">
        {payload.map((entry, index) => (
          <li key={index} className="flex items-center gap-2 text-[11px]">
            <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: entry.color }} aria-hidden />
            <span className="text-muted">{entry.name}</span>
            <span className="ml-auto font-medium tabular-nums text-ink">
              {formatter ? formatter(Number(entry.value), String(entry.name)) : formatNumber(Number(entry.value))}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function axisProps<T extends Record<string, unknown>>(data: T[], key: string) {
  return {
    dataKey: key,
    tick: AXIS_STYLE,
    tickLine: false,
    axisLine: { stroke: GRID_COLOR },
    minTickGap: 24,
  }
}

/* ===================================================================================== */
export function AreaTrend({
  data,
  xKey,
  series,
  height = 260,
  currency,
  formatY = 'number',
  showLegend = true,
}: {
  data: Record<string, any>[]
  xKey: string
  series: { key: string; label: string; color?: string }[]
  height?: number
  currency?: string
  formatY?: 'number' | 'currency' | 'percent'
  showLegend?: boolean
}) {
  const formatValue = useMemo(() => {
    if (formatY === 'currency') return (value: number) => `${currency ?? '$'}${formatCompact(value)}`
    if (formatY === 'percent') return (value: number) => `${Number(value ?? 0).toFixed(1)}%`
    return (value: number) => formatCompact(value)
  }, [formatY, currency])

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
        <defs>
          {series.map((item, index) => (
            <linearGradient key={item.key} id={`grad-${item.key}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={item.color ?? SERIES[index % SERIES.length]} stopOpacity={0.28} />
              <stop offset="100%" stopColor={item.color ?? SERIES[index % SERIES.length]} stopOpacity={0.02} />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={GRID_COLOR} />
        <XAxis {...axisProps(data, xKey)} />
        <YAxis tick={AXIS_STYLE} tickLine={false} axisLine={false} tickFormatter={formatValue} width={52} />
        <Tooltip content={<ChartTooltip formatter={(value) => formatValue(value)} />} cursor={{ stroke: GRID_COLOR }} />
        {showLegend && series.length > 1 ? (
          <Legend wrapperStyle={{ fontSize: 11, color: 'var(--text-muted)' }} iconType="circle" iconSize={7} />
        ) : null}
        {series.map((item, index) => (
          <Area
            key={item.key}
            type="monotone"
            dataKey={item.key}
            name={item.label}
            stroke={item.color ?? SERIES[index % SERIES.length]}
            strokeWidth={2}
            fill={`url(#grad-${item.key})`}
            dot={false}
            activeDot={{ r: 3.5 }}
            connectNulls
            isAnimationActive={false}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  )
}

export function LineTrend({
  data,
  xKey,
  series,
  height = 260,
  formatY = 'number',
  reference,
}: {
  data: Record<string, any>[]
  xKey: string
  series: { key: string; label: string; color?: string }[]
  height?: number
  formatY?: 'number' | 'currency' | 'percent'
  reference?: number
}) {
  const formatValue = (value: number) =>
    formatY === 'currency'
      ? `${formatCompact(value)}`
      : formatY === 'percent'
        ? `${Number(value ?? 0).toFixed(1)}%`
        : formatCompact(value)

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={GRID_COLOR} />
        <XAxis {...axisProps(data, xKey)} />
        <YAxis tick={AXIS_STYLE} tickLine={false} axisLine={false} tickFormatter={formatValue} width={52} />
        <Tooltip content={<ChartTooltip formatter={(value) => formatValue(value)} />} cursor={{ stroke: GRID_COLOR }} />
        {series.length > 1 ? (
          <Legend wrapperStyle={{ fontSize: 11, color: 'var(--text-muted)' }} iconType="circle" iconSize={7} />
        ) : null}
        {reference !== undefined ? (
          <Line
            dataKey={() => reference}
            name="reference"
            stroke="var(--text-subtle)"
            strokeDasharray="4 4"
            dot={false}
            legendType="none"
            isAnimationActive={false}
          />
        ) : null}
        {series.map((item, index) => (
          <Line
            key={item.key}
            type="monotone"
            dataKey={item.key}
            name={item.label}
            stroke={item.color ?? SERIES[index % SERIES.length]}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 3.5 }}
            connectNulls
            isAnimationActive={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}

export function BarSeries({
  data,
  xKey,
  bars,
  height = 260,
  horizontal = false,
  formatY = 'number',
  stacked = false,
  onBarClick,
}: {
  data: Record<string, any>[]
  xKey: string
  bars: { key: string; label: string; color?: string }[]
  height?: number
  horizontal?: boolean
  formatY?: 'number' | 'currency' | 'percent'
  stacked?: boolean
  onBarClick?: (row: Record<string, any>) => void
}) {
  const formatValue = (value: number) =>
    formatY === 'currency'
      ? formatCompact(value)
      : formatY === 'percent'
        ? `${Number(value ?? 0).toFixed(1)}%`
        : formatCompact(value)

  if (horizontal) {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 0, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke={GRID_COLOR} />
          <XAxis type="number" tick={AXIS_STYLE} tickLine={false} axisLine={false} tickFormatter={formatValue} />
          <YAxis type="category" dataKey={xKey} tick={AXIS_STYLE} tickLine={false} axisLine={false} width={130} />
          <Tooltip content={<ChartTooltip formatter={(value) => formatValue(value)} />} cursor={{ fill: GRID_COLOR, opacity: 0.25 }} />
          {bars.map((bar, index) => (
            <Bar
              key={bar.key}
              dataKey={bar.key}
              name={bar.label}
              fill={bar.color ?? SERIES[index % SERIES.length]}
              radius={[0, 5, 5, 0]}
              barSize={16}
              isAnimationActive={false}
              onClick={(entry: any) => onBarClick?.(entry?.payload)}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={GRID_COLOR} />
        <XAxis {...axisProps(data, xKey)} />
        <YAxis tick={AXIS_STYLE} tickLine={false} axisLine={false} tickFormatter={formatValue} width={52} />
        <Tooltip
          content={<ChartTooltip formatter={(value) => formatValue(value)} />}
          cursor={{ fill: GRID_COLOR, opacity: 0.25 }}
        />
        {bars.length > 1 ? (
          <Legend wrapperStyle={{ fontSize: 11, color: 'var(--text-muted)' }} iconType="circle" iconSize={7} />
        ) : null}
        {bars.map((bar, index) => (
          <Bar
            key={bar.key}
            dataKey={bar.key}
            name={bar.label}
            stackId={stacked ? 'stack' : undefined}
            fill={bar.color ?? SERIES[index % SERIES.length]}
            radius={stacked ? 0 : [5, 5, 0, 0]}
            maxBarSize={38}
            isAnimationActive={false}
            onClick={(entry: any) => onBarClick?.(entry?.payload)}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  )
}

export function DonutChart({
  data,
  height = 240,
  valueKey = 'value',
  nameKey = 'name',
  centerLabel,
  onSliceClick,
}: {
  data: Record<string, any>[]
  height?: number
  valueKey?: string
  nameKey?: string
  centerLabel?: ReactNode
  onSliceClick?: (row: Record<string, any>) => void
}) {
  const total = data.reduce((sum, item) => sum + Number(item[valueKey] ?? 0), 0)
  return (
    <div className="relative" style={{ height }}>
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Pie
            data={data}
            dataKey={valueKey}
            nameKey={nameKey}
            innerRadius="58%"
            outerRadius="86%"
            paddingAngle={2}
            stroke="none"
            isAnimationActive={false}
            onClick={(entry: any) => onSliceClick?.(entry?.payload)}
          >
            {data.map((item, index) => (
              <Cell key={index} fill={SERIES[index % SERIES.length]} />
            ))}
          </Pie>
          <Tooltip content={<ChartTooltip />} />
        </PieChart>
      </ResponsiveContainer>
      {centerLabel ? (
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <p className="text-xl font-semibold tabular-nums">{formatCompact(total)}</p>
          <p className="text-[10px] uppercase tracking-wide text-subtle">{centerLabel}</p>
        </div>
      ) : null}
    </div>
  )
}

export function RadarCompare({
  data,
  series,
  height = 260,
  // Accepted for caller symmetry: the radar labels itself from the "axis" field of each row.
  axes: _axes,
}: {
  data: Record<string, any>[]
  axes: string[]
  series: { key: string; label: string; color?: string }[]
  height?: number
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <RadarChart data={data} outerRadius="72%">
        <PolarGrid stroke={GRID_COLOR} />
        <PolarAngleAxis dataKey="axis" tick={AXIS_STYLE} />
        <Tooltip content={<ChartTooltip />} />
        {series.map((item, index) => (
          <Radar
            key={item.key}
            dataKey={item.key}
            name={item.label}
            stroke={item.color ?? SERIES[index % SERIES.length]}
            fill={item.color ?? SERIES[index % SERIES.length]}
            fillOpacity={0.18}
            isAnimationActive={false}
          />
        ))}
      </RadarChart>
    </ResponsiveContainer>
  )
}

export function HeatmapStrip({
  data,
  valueKey,
  height = 60,
  colorFor,
}: {
  data: ({ label: string } & Record<string, any>)[]
  valueKey: string
  height?: number
  colorFor?: (value: number) => string
}) {
  const max = Math.max(...data.map((item) => Number(item[valueKey] ?? 0)), 1)
  return (
    <div className="flex items-end gap-0.5 overflow-x-auto no-scrollbar" style={{ height }} aria-hidden>
      {data.map((item, index) => {
        const value = Number(item[valueKey] ?? 0)
        const intensity = value / max
        return (
          <div
            key={index}
            title={`${item.label}: ${formatNumber(value)}`}
            className="min-w-[6px] flex-1 rounded-sm"
            style={{
              height: `${Math.max(8, intensity * 100)}%`,
              backgroundColor: colorFor ? colorFor(value) : `color-mix(in srgb, var(--chart-1) ${25 + intensity * 75}%, transparent)`,
            }}
          />
        )
      })}
    </div>
  )
}

export function ChartFrame({ children, height, className }: { children: ReactNode; height: number; className?: string }) {
  return <div className={cn('w-full', className)} style={{ height }}>{children}</div>
}

export { SERIES as CHART_SERIES }