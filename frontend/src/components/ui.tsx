/**
 * Shared UI primitives.
 *
 * Everything the pages need is here so the screens stay declarative: cards, stat
 * tiles, badges, tables with sorting + pagination, modals, drawers, toasts, tabs,
 * empty/loading/error states and the icon button.
 */

import {
  type ReactNode,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type SelectHTMLAttributes,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from 'react'
import { AlertCircle, Check, ChevronDown, ChevronLeft, ChevronRight, Inbox, Loader2, Search, X } from 'lucide-react'
import { cn } from '@/lib/cn'

/* =====================================================================================
   Card
   ===================================================================================== */
export function Card({
  children,
  className,
  padded = true,
  hover = false,
  as: Component = 'div',
}: {
  children: ReactNode
  className?: string
  padded?: boolean
  hover?: boolean
  as?: 'div' | 'section' | 'article'
}) {
  return (
    <Component className={cn('card', padded && 'p-4 sm:p-5', hover && 'card-hover', className)}>{children}</Component>
  )
}

export function CardHeader({
  title,
  subtitle,
  action,
  icon,
  className,
}: {
  title: ReactNode
  subtitle?: ReactNode
  action?: ReactNode
  icon?: ReactNode
  className?: string
}) {
  return (
    <div className={cn('mb-4 flex items-start justify-between gap-3', className)}>
      <div className="flex min-w-0 items-start gap-2.5">
        {icon ? <span className="mt-0.5 shrink-0 text-brand-600 dark:text-brand-300">{icon}</span> : null}
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold text-ink">{title}</h3>
          {subtitle ? <p className="mt-0.5 text-xs text-subtle">{subtitle}</p> : null}
        </div>
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  )
}

/* =====================================================================================
   Buttons
   ===================================================================================== */
type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md'
  loading?: boolean
  icon?: ReactNode
}

export function Button({
  variant = 'secondary',
  size = 'md',
  loading = false,
  icon,
  children,
  className,
  disabled,
  ...props
}: ButtonProps) {
  return (
    <button
      {...props}
      disabled={disabled || loading}
      className={cn(
        'btn',
        variant === 'primary' && 'btn-primary',
        variant === 'secondary' && 'btn-secondary',
        variant === 'ghost' && 'btn-ghost',
        variant === 'danger' && 'btn-danger',
        size === 'sm' && 'btn-sm',
        className,
      )}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  )
}

export function IconButton({
  label,
  icon,
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string; icon: ReactNode }) {
  return (
    <button
      {...props}
      aria-label={label}
      title={label}
      className={cn('btn btn-ghost h-9 w-9 !p-0', className)}
    >
      {icon}
    </button>
  )
}

/* =====================================================================================
   Badges
   ===================================================================================== */
export type Tone = 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'brand'

const TONE_CLASS: Record<Tone, string> = {
  success: 'badge-success',
  warning: 'badge-warning',
  danger: 'badge-danger',
  info: 'badge-info',
  neutral: 'badge-neutral',
  brand: 'bg-brand-100 text-brand-700 dark:bg-brand-500/20 dark:text-brand-200 border-brand-300/40',
}

export function Badge({
  children,
  tone = 'neutral',
  className,
  dot = false,
}: {
  children: ReactNode
  tone?: Tone
  className?: string
  dot?: boolean
}) {
  return (
    <span className={cn('badge', TONE_CLASS[tone], className)}>
      {dot ? <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden /> : null}
      {children}
    </span>
  )
}

/** Coloured price movement pill (red = price up, green = price down). */
export function DeltaPill({ value, digits = 1, suffix = '%' }: { value: number | null | undefined; digits?: number; suffix?: string }) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return <span className="text-subtle">—</span>
  }
  const numeric = Number(value)
  const tone: Tone = Math.abs(numeric) < 0.01 ? 'neutral' : numeric < 0 ? 'success' : 'danger'
  const arrow = numeric > 0 ? '↑' : numeric < 0 ? '↓' : '→'
  return (
    <span className={cn('badge tabular-nums', TONE_CLASS[tone])}>
      {arrow} {Math.abs(numeric).toFixed(digits)}
      {suffix}
    </span>
  )
}

/* =====================================================================================
   Stat tile
   ===================================================================================== */
export function StatTile({
  label,
  value,
  hint,
  icon,
  tone = 'brand',
  delta,
  onClick,
}: {
  label: string
  value: ReactNode
  hint?: ReactNode
  icon?: ReactNode
  tone?: Tone
  delta?: ReactNode
  onClick?: () => void
}) {
  const accent: Record<Tone, string> = {
    brand: 'text-brand-600 dark:text-brand-300 bg-brand-100/70 dark:bg-brand-500/15',
    success: 'text-success bg-success-soft',
    warning: 'text-warning bg-warning-soft',
    danger: 'text-danger bg-danger-soft',
    info: 'text-info bg-info-soft',
    neutral: 'text-muted bg-surface-3',
  }
  const Component = onClick ? 'button' : 'div'
  return (
    <Component
      onClick={onClick}
      className={cn('card card-hover flex items-start gap-3 p-4 text-left', onClick && 'hover:border-brand-400 dark:hover:border-brand-500')}
    >
      {icon ? (
        <span className={cn('flex h-9 w-9 shrink-0 items-center justify-center rounded-lg', accent[tone])} aria-hidden>
          {icon}
        </span>
      ) : null}
      <div className="min-w-0 flex-1">
        <p className="stat-label truncate">{label}</p>
        <p className="stat-value mt-0.5 truncate">{value}</p>
        {hint ? <p className="mt-0.5 truncate text-xs text-subtle">{hint}</p> : null}
        {delta ? <div className="mt-1.5">{delta}</div> : null}
      </div>
    </Component>
  )
}

/* =====================================================================================
   Form controls
   ===================================================================================== */
export function TextInput({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cn('input', className)} />
}

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...props} className={cn('input', className)}>
      {children}
    </select>
  )
}

export function SearchInput({
  value,
  onChange,
  placeholder = 'Search…',
  className,
}: {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  className?: string
}) {
  return (
    <div className={cn('relative', className)}>
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-subtle" aria-hidden />
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        aria-label={placeholder}
        className="input pl-9 pr-8"
      />
      {value ? (
        <button
          onClick={() => onChange('')}
          aria-label="Clear search"
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-subtle hover:bg-surface-3"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      ) : null}
    </div>
  )
}

export function Toggle({
  checked,
  onChange,
  label,
  description,
  disabled,
}: {
  checked: boolean
  onChange: (next: boolean) => void
  label?: ReactNode
  description?: ReactNode
  disabled?: boolean
}) {
  return (
    <label className={cn('flex cursor-pointer items-start gap-3', disabled && 'cursor-not-allowed opacity-60')}>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          'relative mt-0.5 h-5 w-9 shrink-0 rounded-full border transition-colors',
          checked ? 'border-brand-500 bg-brand-500' : 'border-line bg-surface-3',
        )}
      >
        <span
          className="absolute top-0.5 h-3.5 w-3.5 rounded-full bg-white shadow transition-all"
          style={{ insetInlineStart: checked ? '1.125rem' : '0.125rem' }}
        />
      </button>
      {label || description ? (
        <span className="min-w-0">
          {label ? <span className="block text-sm font-medium text-ink">{label}</span> : null}
          {description ? <span className="block text-xs text-subtle">{description}</span> : null}
        </span>
      ) : null}
    </label>
  )
}

export function Checkbox({
  checked,
  onChange,
  label,
}: {
  checked: boolean
  onChange: (next: boolean) => void
  label?: ReactNode
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-sm text-ink">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} className="accent-brand-600" />
      {label}
    </label>
  )
}

/* =====================================================================================
   Tabs
   ===================================================================================== */
export function Tabs({
  tabs,
  active,
  onChange,
  className,
}: {
  tabs: { id: string; label: string; count?: number; icon?: ReactNode }[]
  active: string
  onChange: (id: string) => void
  className?: string
}) {
  return (
    <div className={cn('flex gap-1 overflow-x-auto border-b border-line no-scrollbar', className)} role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          role="tab"
          aria-selected={active === tab.id}
          onClick={() => onChange(tab.id)}
          className={cn(
            'relative flex shrink-0 items-center gap-2 whitespace-nowrap px-3 py-2 text-sm font-medium',
            active === tab.id ? 'text-brand-700 dark:text-brand-300' : 'text-muted hover:text-ink',
          )}
        >
          {tab.icon}
          {tab.label}
          {typeof tab.count === 'number' ? (
            <span className="rounded-full bg-surface-3 px-1.5 py-0.5 text-[10px] font-semibold text-muted">{tab.count}</span>
          ) : null}
          {active === tab.id ? <span className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-brand-600" /> : null}
        </button>
      ))}
    </div>
  )
}

/* =====================================================================================
   Segmented control
   ===================================================================================== */
export function Segmented({
  options,
  value,
  onChange,
  size = 'md',
  className,
}: {
  options: { id: string; label: string }[]
  value: string
  onChange: (id: string) => void
  size?: 'sm' | 'md'
  className?: string
}) {
  return (
    <div className={cn('inline-flex rounded-lg border border-line bg-surface-3 p-0.5', className)} role="group">
      {options.map((option) => (
        <button
          key={option.id}
          onClick={() => onChange(option.id)}
          aria-pressed={value === option.id}
          className={cn(
            'rounded-md font-medium text-muted hover:text-ink',
            size === 'sm' ? 'px-2 py-1 text-xs' : 'px-3 py-1 text-sm',
            value === option.id && 'bg-surface text-ink shadow-sm',
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

/* =====================================================================================
   Table
   ===================================================================================== */
export type Column<T> = {
  key: string
  header: ReactNode
  render: (row: T, index: number) => ReactNode
  sortValue?: (row: T) => string | number | null
  align?: 'left' | 'right' | 'center'
  width?: string
  hideBelow?: 'sm' | 'md' | 'lg' | 'xl'
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
  sort,
  onSort,
  emptyMessage = 'No records found',
  loading = false,
  skeletonRows = 6,
  maxHeight,
  dense = false,
}: {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T, index: number) => string
  onRowClick?: (row: T) => void
  sort?: { by?: string; dir: 'asc' | 'desc' }
  onSort?: (key: string) => void
  emptyMessage?: string
  loading?: boolean
  skeletonRows?: number
  maxHeight?: number | string
  dense?: boolean
}) {
  const hideClass: Record<string, string> = {
    sm: 'hidden sm:table-cell',
    md: 'hidden md:table-cell',
    lg: 'hidden lg:table-cell',
    xl: 'hidden xl:table-cell',
  }
  const alignment = (align?: Column<T>['align']) =>
    align === 'right' ? 'text-right' : align === 'center' ? 'text-center' : 'text-left'

  if (loading) {
    return (
      <div className="table-wrap" style={{ maxHeight }}>
        <table className="w-full">
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column.key} className={cn('th', alignment(column.align), column.hideBelow && hideClass[column.hideBelow])}>
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: skeletonRows }).map((_, rowIndex) => (
              <tr key={rowIndex}>
                {columns.map((column) => (
                  <td key={column.key} className={cn(dense ? 'px-3 py-1.5' : 'px-3 py-2.5')}>
                    <div className="skeleton h-4 w-full" />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  if (!rows.length) {
    return (
      <div className="table-wrap flex flex-col items-center justify-center gap-2 py-14 text-center">
        <Inbox className="h-8 w-8 text-subtle" aria-hidden />
        <p className="text-sm text-muted">{emptyMessage}</p>
      </div>
    )
  }

  return (
    <div className="table-wrap" style={{ maxHeight }}>
      <table className="w-full">
        <thead>
          <tr>
            {columns.map((column) => {
              const isActive = sort?.by === column.key
              return (
                <th
                  key={column.key}
                  style={column.width ? { width: column.width } : undefined}
                  className={cn('th', alignment(column.align), column.hideBelow && hideClass[column.hideBelow])}
                  aria-sort={isActive ? (sort?.dir === 'asc' ? 'ascending' : 'descending') : 'none'}
                >
                  {column.sortValue && onSort ? (
                    <button
                      onClick={() => onSort(column.key)}
                      className="inline-flex items-center gap-1 hover:text-ink"
                    >
                      {column.header}
                      <ChevronDown
                        className={cn('h-3.5 w-3.5', isActive ? 'opacity-100' : 'opacity-30', isActive && sort?.dir === 'asc' && 'rotate-180')}
                      />
                    </button>
                  ) : (
                    column.header
                  )}
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr
              key={rowKey(row, index)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={cn('row-hover', onRowClick && 'cursor-pointer')}
            >
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={cn('td', alignment(column.align), dense && '!py-1.5', column.hideBelow && hideClass[column.hideBelow])}
                >
                  {column.render(row, index)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Pagination({
  page,
  pageSize,
  total,
  onPage,
  onPageSize,
}: {
  page: number
  pageSize: number
  total: number
  onPage: (page: number) => void
  onPageSize?: (size: number) => void
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1
  const to = Math.min(total, page * pageSize)
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 pt-3 text-sm text-muted">
      <p>
        Showing <span className="font-medium text-ink tabular-nums">{from}</span>-
        <span className="font-medium text-ink tabular-nums">{to}</span> of{' '}
        <span className="font-medium text-ink tabular-nums">{total.toLocaleString()}</span>
      </p>
      <div className="flex items-center gap-2">
        {onPageSize ? (
          <select
            value={pageSize}
            onChange={(event) => onPageSize(Number(event.target.value))}
            aria-label="Rows per page"
            className="input h-8 w-20 py-0 text-xs"
          >
            {[10, 25, 50, 100, 200].map((size) => (
              <option key={size} value={size}>
                {size} / page
              </option>
            ))}
          </select>
        ) : null}
        <div className="flex items-center gap-1">
          <IconButton label="Previous page" icon={<ChevronLeft className="h-4 w-4" />} disabled={page <= 1} onClick={() => onPage(page - 1)} />
          <span className="px-2 text-xs tabular-nums text-muted">
            {page} / {pages}
          </span>
          <IconButton label="Next page" icon={<ChevronRight className="h-4 w-4" />} disabled={page >= pages} onClick={() => onPage(page + 1)} />
        </div>
      </div>
    </div>
  )
}

/* =====================================================================================
   Modal / Drawer
   ===================================================================================== */
export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = 'md',
}: {
  open: boolean
  onClose: () => void
  title: ReactNode
  description?: ReactNode
  children?: ReactNode
  footer?: ReactNode
  size?: 'sm' | 'md' | 'lg' | 'xl'
}) {
  const titleId = useId()
  useEffect(() => {
    if (!open) return
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  if (!open) return null
  const width = { sm: 'max-w-sm', md: 'max-w-lg', lg: 'max-w-2xl', xl: 'max-w-4xl' }[size]
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-4">
      <div className="absolute inset-0 bg-[var(--overlay)]" onClick={onClose} aria-hidden />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={cn(
          'relative w-full rounded-t-2xl border border-line bg-surface shadow-pop sm:rounded-2xl',
          width,
          'max-h-[92vh] overflow-auto',
        )}
      >
        <div className="flex items-start justify-between gap-4 border-b border-line p-4 sm:p-5">
          <div className="min-w-0">
            <h2 id={titleId} className="text-base font-semibold text-ink">
              {title}
            </h2>
            {description ? <p className="mt-0.5 text-xs text-subtle">{description}</p> : null}
          </div>
          <IconButton label="Close" icon={<X className="h-4 w-4" />} onClick={onClose} />
        </div>
        {children ? <div className="p-4 sm:p-5">{children}</div> : null}
        {footer ? <div className="flex justify-end gap-2 border-t border-line p-4">{footer}</div> : null}
      </div>
    </div>
  )
}

export function Drawer({
  open,
  onClose,
  title,
  children,
  width = 'max-w-lg',
}: {
  open: boolean
  onClose: () => void
  title: ReactNode
  children: ReactNode
  width?: string
}) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-[var(--overlay)]" onClick={onClose} aria-hidden />
      <aside className={cn('relative h-full w-full border-l border-line bg-surface shadow-pop', width)} role="dialog" aria-modal="true">
        <div className="flex items-center justify-between border-b border-line p-4">
          <h2 className="text-base font-semibold text-ink">{title}</h2>
          <IconButton label="Close drawer" icon={<X className="h-4 w-4" />} onClick={onClose} />
        </div>
        <div className="h-[calc(100%-3.5rem)] overflow-auto p-4">{children}</div>
      </aside>
    </div>
  )
}

/* =====================================================================================
   States: loading / error / empty
   ===================================================================================== */
export function LoadingState({ label = 'Loading…', rows = 4 }: { label?: string; rows?: number }) {
  return (
    <div className="space-y-3" role="status" aria-live="polite">
      <div className="flex items-center gap-2 text-sm text-muted">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
        {label}
      </div>
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="skeleton h-16 w-full" />
      ))}
    </div>
  )
}

export function ErrorState({
  title = 'Something went wrong',
  message,
  onRetry,
}: {
  title?: string
  message?: ReactNode
  onRetry?: () => void
}) {
  return (
    <div className="card flex flex-col items-center gap-3 border-danger/30 bg-danger-soft/40 p-8 text-center">
      <AlertCircle className="h-8 w-8 text-danger" aria-hidden />
      <div>
        <p className="text-sm font-semibold text-ink">{title}</p>
        {message ? <p className="mt-1 max-w-md text-xs text-muted">{message}</p> : null}
      </div>
      {onRetry ? (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Try again
        </Button>
      ) : null}
    </div>
  )
}

export function EmptyState({
  title = 'Nothing here yet',
  message,
  action,
  icon,
}: {
  title?: string
  message?: ReactNode
  action?: ReactNode
  icon?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
      <span className="text-subtle">{icon ?? <Inbox className="h-7 w-7" aria-hidden />}</span>
      <p className="text-sm font-medium text-ink">{title}</p>
      {message ? <p className="max-w-sm text-xs text-subtle">{message}</p> : null}
      {action}
    </div>
  )
}

/* =====================================================================================
   Toasts
   ===================================================================================== */
type Toast = { id: number; level: 'success' | 'error' | 'info' | 'warning'; title: string; description?: string }

const ToastContext = createContext<{ push: (toast: Omit<Toast, 'id'>) => void }>({ push: () => {} })

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const counter = useRef(0)

  const push = useCallback((toast: Omit<Toast, 'id'>) => {
    counter.current += 1
    const id = counter.current
    setToasts((current) => [...current, { ...toast, id }])
    window.setTimeout(() => setToasts((current) => current.filter((item) => item.id !== id)), 5000)
  }, [])

  const value = useMemo(() => ({ push }), [push])
  const toneClass: Record<Toast['level'], string> = {
    success: 'border-success/40 bg-success-soft text-success',
    error: 'border-danger/40 bg-danger-soft text-danger',
    info: 'border-info/40 bg-info-soft text-info',
    warning: 'border-warning/40 bg-warning-soft text-warning',
  }

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-[min(22rem,calc(100vw-2rem))] flex-col gap-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role="status"
            className={cn('pointer-events-auto flex items-start gap-2 rounded-xl border p-3 shadow-pop', toneClass[toast.level])}
          >
            {toast.level === 'success' ? <Check className="mt-0.5 h-4 w-4 shrink-0" /> : <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />}
            <div className="min-w-0 text-ink">
              <p className="text-sm font-medium">{toast.title}</p>
              {toast.description ? <p className="text-xs text-muted">{toast.description}</p> : null}
            </div>
            <button
              onClick={() => setToasts((current) => current.filter((item) => item.id !== toast.id))}
              className="ml-auto rounded p-0.5 text-subtle hover:bg-surface-3"
              aria-label="Dismiss"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const { push } = useContext(ToastContext)
  return useMemo(
    () => ({
      success: (title: string, description?: string) => push({ level: 'success', title, description }),
      error: (title: string, description?: string) => push({ level: 'error', title, description }),
      info: (title: string, description?: string) => push({ level: 'info', title, description }),
      warning: (title: string, description?: string) => push({ level: 'warning', title, description }),
    }),
    [push],
  )
}

/* =====================================================================================
   Misc
   ===================================================================================== */
export function ProgressBar({ value, tone = 'brand', className }: { value: number; tone?: 'brand' | 'success' | 'warning' | 'danger'; className?: string }) {
  const colors = { brand: 'bg-brand-500', success: 'bg-success', warning: 'bg-warning', danger: 'bg-danger' }
  return (
    <div className={cn('h-2 w-full overflow-hidden rounded-full bg-surface-3', className)}>
      <div className={cn('h-full rounded-full', colors[tone])} style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
    </div>
  )
}

export function KeyValue({ items, columns = 2 }: { items: { label: string; value: ReactNode }[]; columns?: 1 | 2 | 3 }) {
  const grid = { 1: 'grid-cols-1', 2: 'sm:grid-cols-2', 3: 'sm:grid-cols-2 lg:grid-cols-3' }[columns]
  return (
    <dl className={cn('grid gap-3', grid)}>
      {items.map((item) => (
        <div key={item.label} className="min-w-0">
          <dt className="stat-label">{item.label}</dt>
          <dd className="mt-0.5 truncate text-sm font-medium text-ink">{item.value}</dd>
        </div>
      ))}
    </dl>
  )
}

export function Sparkline({ values, className }: { values: number[]; className?: string }) {
  if (!values.length) return null
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const points = values
    .map((value, index) => {
      const x = (index / Math.max(1, values.length - 1)) * 100
      const y = 100 - ((value - min) / span) * 100
      return `${x.toFixed(2)},${y.toFixed(2)}`
    })
    .join(' ')
  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" className={cn('h-8 w-24', className)} aria-hidden>
      <polyline points={points} fill="none" stroke="var(--chart-1)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

export function ChipGroup({
  options,
  value,
  onChange,
  className,
}: {
  options: { id: string; label: string; count?: number }[]
  value: string
  onChange: (id: string) => void
  className?: string
}) {
  return (
    <div className={cn('flex flex-wrap gap-1.5', className)}>
      {options.map((option) => (
        <button
          key={option.id}
          onClick={() => onChange(option.id)}
          aria-pressed={value === option.id}
          className={cn(
            'rounded-full border px-2.5 py-1 text-xs font-medium',
            value === option.id
              ? 'border-brand-500 bg-brand-600 text-white'
              : 'border-line bg-surface text-muted hover:border-line-strong hover:text-ink',
          )}
        >
          {option.label}
          {typeof option.count === 'number' ? <span className="ml-1 tabular-nums opacity-75">{option.count}</span> : null}
        </button>
      ))}
    </div>
  )
}