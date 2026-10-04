/**
 * Users: account directory, role mix and API key management.
 *
 * Admin-only (the router guards `manage_users`). Plain API keys are returned once
 * on creation, so the issued secret lives in local state and is discarded as soon
 * as the modal closes.
 */

import { type ReactNode, useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  Copy,
  Eye,
  EyeOff,
  KeyRound,
  LogIn,
  Plus,
  ShieldAlert,
  Trash2,
  UserCheck,
  UserPlus,
  UserX,
  Users as UsersIcon,
} from 'lucide-react'

import { CHART_SERIES, DonutChart } from '@/components/charts'
import {
  Badge,
  Button,
  Card,
  CardHeader,
  DataTable,
  Drawer,
  EmptyState,
  ErrorState,
  IconButton,
  KeyValue,
  LoadingState,
  Modal,
  Pagination,
  Select,
  StatTile,
  TextInput,
  useToast,
  type Column,
  type Tone,
} from '@/components/ui'
import { endpoints } from '@/lib/api'
import { useApiQuery } from '@/hooks/useApi'
import { formatDateTime, formatNumber, formatRelative, initials, titleCase } from '@/lib/format'

type UserRow = {
  user_id: number
  email: string
  full_name: string
  role: string
  job_title: string | null
  department: string | null
  is_active: boolean
  login_count: number
  last_login_at: string | null
  created_at: string | null
}

type UserStats = {
  total_users: number
  active_users: number
  logins_24h: number
  logins_7d: number
  locked_users: number
  api_keys: number
  by_role: Record<string, number>
  top_users: { user_id: number; full_name: string; email: string; login_count: number }[]
}

type ApiKeyRow = {
  key_id: number
  name: string
  prefix: string
  is_active: boolean
  created_at: string
  last_used_at: string | null
  usage_count: number
  expires_at: string | null
}

type IssuedKey = ApiKeyRow & { api_key: string }

type FormState = { email: string; fullName: string; password: string; role: string; jobTitle: string; department: string }
type FormErrors = Partial<Record<keyof FormState, string>>

const EMPTY_FORM: FormState = { email: '', fullName: '', password: '', role: 'viewer', jobTitle: '', department: '' }

const ROLES = [
  { id: 'viewer', label: 'Viewer — read-only dashboards' },
  { id: 'analyst', label: 'Analyst — read, query and export' },
  { id: 'admin', label: 'Admin — full control' },
]

function roleTone(role: string): Tone {
  return role === 'admin' ? 'brand' : role === 'analyst' ? 'info' : 'neutral'
}

/** Mirrors the server-side strength gate so the user sees problems before submitting. */
function passwordProblems(password: string): string[] {
  const problems: string[] = []
  if (password.length < 10) problems.push('at least 10 characters')
  if (!/\d/.test(password)) problems.push('at least one digit')
  if (!/[A-Z]/.test(password)) problems.push('at least one uppercase letter')
  if (!/[a-z]/.test(password)) problems.push('at least one lowercase letter')
  if (!/[^A-Za-z0-9]/.test(password)) problems.push('at least one symbol')
  return problems
}

export default function Users() {
  const queryClient = useQueryClient()
  const toast = useToast()

  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  const [formOpen, setFormOpen] = useState(false)
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [formErrors, setFormErrors] = useState<FormErrors>({})
  const [showPassword, setShowPassword] = useState(false)
  const [keysFor, setKeysFor] = useState<UserRow | null>(null)
  const [keyFormOpen, setKeyFormOpen] = useState(false)
  const [keyName, setKeyName] = useState('')
  const [keyNameError, setKeyNameError] = useState<string | undefined>(undefined)
  const [issued, setIssued] = useState<IssuedKey | null>(null)

  const users = useApiQuery<{ items?: UserRow[]; total?: number }>(
    ['users', page, pageSize],
    () => endpoints.users({ page, page_size: pageSize }),
  )
  const stats = useApiQuery<UserStats>(['user-stats'], endpoints.userStats, { staleTime: 30_000 })

  const rows = users.data?.items ?? []
  const total = Number(users.data?.total ?? 0)
  const keyUserId = keysFor?.user_id ?? null
  const keys = useApiQuery<ApiKeyRow[]>(
    ['api-keys', keyUserId],
    () => endpoints.apiKeys(Number(keyUserId)),
    { enabled: keyUserId !== null },
  )

  const roleMix = useMemo(
    () =>
      Object.entries(stats.data?.by_role ?? {})
        .map(([role, count]) => ({ name: titleCase(role), value: Number(count ?? 0) }))
        .filter((item) => item.value > 0)
        .sort((left, right) => right.value - left.value),
    [stats.data],
  )

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['users'] })
    void queryClient.invalidateQueries({ queryKey: ['user-stats'] })
    void queryClient.invalidateQueries({ queryKey: ['api-keys'] })
  }

  const createUser = useMutation({
    mutationFn: (payload: Record<string, unknown>) => endpoints.createUser(payload),
    onSuccess: () => {
      toast.success('User created', form.email)
      setFormOpen(false)
      setForm(EMPTY_FORM)
      invalidate()
    },
    onError: (error: Error) => toast.error('Could not create the user', error.message),
  })

  const deactivateUser = useMutation({
    mutationFn: (id: number) => endpoints.deactivateUser(id),
    onSuccess: (_result, id) => {
      toast.success('User deactivated', `Access revoked for user #${id}`)
      invalidate()
    },
    onError: (error: Error) => toast.error('Could not deactivate the user', error.message),
  })

  const activateUser = useMutation({
    mutationFn: (id: number) => endpoints.updateUser(id, { is_active: true }) as Promise<UserRow>,
    onSuccess: (result) => {
      if (result?.is_active) toast.success('User activated')
      else toast.warning('Account still deactivated', 'The API accepted the request but did not change the account state.')
      invalidate()
    },
    onError: (error: Error) => toast.error('Could not activate the user', error.message),
  })

  const createKey = useMutation({
    mutationFn: ({ userId, name }: { userId: number; name: string }) => endpoints.createApiKey(userId, name),
    onSuccess: (result: IssuedKey) => {
      setKeyFormOpen(false)
      setKeyName('')
      setKeyNameError(undefined)
      setIssued(result)
      invalidate()
    },
    onError: (error: Error) => toast.error('Could not create the API key', error.message),
  })

  const revokeKey = useMutation({
    mutationFn: ({ userId, keyId }: { userId: number; keyId: number }) => endpoints.revokeApiKey(userId, keyId),
    onSuccess: () => {
      toast.success('API key revoked')
      invalidate()
    },
    onError: (error: Error) => toast.error('Could not revoke the key', error.message),
  })

  function validate(): FormErrors {
    const errors: FormErrors = {}
    const email = form.email.trim()
    if (!email) errors.email = 'Email is required'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errors.email = 'Enter a valid email address'
    const name = form.fullName.trim()
    if (!name) errors.fullName = 'Full name is required'
    else if (name.length < 2) errors.fullName = 'Use at least 2 characters'
    const problems = passwordProblems(form.password)
    if (problems.length) errors.password = `Password needs ${problems.join(', ')}`
    if (!ROLES.some((role) => role.id === form.role)) errors.role = 'Choose a role'
    return errors
  }

  function submit() {
    const errors = validate()
    setFormErrors(errors)
    if (Object.keys(errors).length) return
    createUser.mutate({
      email: form.email.trim(),
      full_name: form.fullName.trim(),
      password: form.password,
      role: form.role,
      job_title: form.jobTitle.trim() || null,
      department: form.department.trim() || null,
    })
  }

  async function copyIssuedKey() {
    if (!issued) return
    try {
      await navigator.clipboard.writeText(issued.api_key)
      toast.success('API key copied to the clipboard')
    } catch {
      toast.error('Copy failed', 'Select the key text and copy it manually.')
    }
  }

  const columns: Column<UserRow>[] = [
    {
      key: 'user',
      header: 'User',
      sortValue: (row) => row.full_name,
      render: (row) => (
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-100 text-[11px] font-semibold text-brand-700 dark:bg-brand-500/20 dark:text-brand-200">
            {initials(row.full_name || row.email)}
          </span>
          <div className="min-w-0">
            <p className="max-w-[14rem] truncate font-medium text-ink">{row.full_name}</p>
            <p className="max-w-[14rem] truncate text-xs text-subtle">{row.email}</p>
          </div>
        </div>
      ),
    },
    { key: 'role', header: 'Role', sortValue: (row) => row.role, render: (row) => <Badge tone={roleTone(row.role)}>{titleCase(row.role)}</Badge> },
    {
      key: 'org',
      header: 'Team',
      hideBelow: 'lg',
      render: (row) => (
        <div className="min-w-0">
          <p className="max-w-[12rem] truncate text-xs text-ink">{row.job_title ?? '—'}</p>
          <p className="max-w-[12rem] truncate text-[11px] text-subtle">{row.department ?? ''}</p>
        </div>
      ),
    },
    {
      key: 'state',
      header: 'State',
      align: 'center',
      render: (row) => <Badge tone={row.is_active ? 'success' : 'neutral'} dot>{row.is_active ? 'Active' : 'Disabled'}</Badge>,
    },
    {
      key: 'last_login',
      header: 'Last login',
      align: 'right',
      hideBelow: 'sm',
      sortValue: (row) => (row.last_login_at ? new Date(row.last_login_at).getTime() : 0),
      render: (row) => (
        <span className="text-xs text-muted" title={formatDateTime(row.last_login_at)}>
          {formatRelative(row.last_login_at)}
        </span>
      ),
    },
    {
      key: 'logins',
      header: 'Logins',
      align: 'right',
      hideBelow: 'md',
      sortValue: (row) => Number(row.login_count ?? 0),
      render: (row) => <span className="tabular-nums">{formatNumber(row.login_count ?? 0)}</span>,
    },
    {
      key: 'actions',
      header: '',
      align: 'right',
      width: '7rem',
      render: (row) => (
        <div className="flex items-center justify-end gap-1">
          <IconButton label={`API keys for ${row.full_name}`} icon={<KeyRound className="h-4 w-4" />} onClick={() => setKeysFor(row)} />
          {row.is_active ? (
            <IconButton
              label={`Deactivate ${row.full_name}`}
              icon={<UserX className="h-4 w-4 text-danger" />}
              disabled={deactivateUser.isPending}
              onClick={() => deactivateUser.mutate(row.user_id)}
            />
          ) : (
            <IconButton
              label={`Activate ${row.full_name}`}
              icon={<UserCheck className="h-4 w-4 text-success" />}
              disabled={activateUser.isPending}
              onClick={() => activateUser.mutate(row.user_id)}
            />
          )}
        </div>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      {/* --------------------------------------------------------------- KPI tiles */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <StatTile label="Total users" value={formatNumber(stats.data?.total_users ?? 0)} hint="accounts in the directory" icon={<UsersIcon className="h-4 w-4" />} />
        <StatTile
          label="Active"
          value={formatNumber(stats.data?.active_users ?? 0)}
          hint="allowed to sign in"
          icon={<UserCheck className="h-4 w-4" />}
          tone="success"
        />
        <StatTile label="Logins 24h" value={formatNumber(stats.data?.logins_24h ?? 0)} hint="in the last day" icon={<LogIn className="h-4 w-4" />} tone="info" />
        <StatTile label="Logins 7d" value={formatNumber(stats.data?.logins_7d ?? 0)} hint="in the last week" icon={<LogIn className="h-4 w-4" />} tone="info" />
        <StatTile
          label="Locked"
          value={formatNumber(stats.data?.locked_users ?? 0)}
          hint="after failed sign-ins"
          icon={<ShieldAlert className="h-4 w-4" />}
          tone={Number(stats.data?.locked_users ?? 0) > 0 ? 'danger' : 'neutral'}
        />
        <StatTile label="API keys" value={formatNumber(stats.data?.api_keys ?? 0)} hint="active machine keys" icon={<KeyRound className="h-4 w-4" />} tone="warning" />
      </div>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        <Card>
          <CardHeader title="Users by role" subtitle="Share of the directory" icon={<UsersIcon className="h-4 w-4" />} />
          {roleMix.length ? (
            <>
              <DonutChart data={roleMix} height={200} centerLabel="users" />
              <div className="mt-3 space-y-1.5 text-xs">
                {roleMix.map((item, index) => (
                  <div key={item.name} className="flex items-center gap-2">
                    <span
                      className="h-2.5 w-2.5 rounded-full"
                      style={{ backgroundColor: CHART_SERIES[index % CHART_SERIES.length] }}
                      aria-hidden
                    />
                    <span className="text-muted">{item.name}</span>
                    <span className="ml-auto font-medium tabular-nums">{formatNumber(item.value)}</span>
                  </div>
                ))}
              </div>
            </>
          ) : stats.isLoading && !stats.data ? (
            <LoadingState label="Loading role mix…" rows={2} />
          ) : (
            <EmptyState title="No users yet" />
          )}
        </Card>

        <Card className="xl:col-span-2">
          <CardHeader
            title="Most active users"
            subtitle="Ranked by lifetime sign-ins"
            icon={<LogIn className="h-4 w-4" />}
            action={
              <Button size="sm" variant="primary" icon={<UserPlus className="h-4 w-4" />} onClick={() => { setForm(EMPTY_FORM); setFormErrors({}); setFormOpen(true) }}>
                Create user
              </Button>
            }
          />
          {stats.isError ? (
            <ErrorState message={(stats.error as Error)?.message} onRetry={() => stats.refetch()} />
          ) : stats.isLoading && !stats.data ? (
            <LoadingState label="Loading usage statistics…" rows={3} />
          ) : stats.data?.top_users?.length ? (
            <ul className="divide-y divide-line">
              {stats.data.top_users.map((row) => (
                <li key={row.user_id} className="flex items-center gap-3 py-2.5">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-surface-3 text-[11px] font-semibold text-muted">
                    {initials(row.full_name || row.email)}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-ink">{row.full_name}</p>
                    <p className="truncate text-xs text-subtle">{row.email}</p>
                  </div>
                  <Badge tone="neutral">{formatNumber(row.login_count)} logins</Badge>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="No sign-ins recorded yet" />
          )}
        </Card>
      </div>

      {/* --------------------------------------------------------------- directory */}
      <Card padded={false}>
        <div className="p-4 sm:p-5">
          <CardHeader
            title="User directory"
            subtitle="Deactivating an account keeps its audit history but blocks sign-in"
            icon={<UsersIcon className="h-4 w-4" />}
            action={
              <Button size="sm" variant="primary" icon={<UserPlus className="h-4 w-4" />} onClick={() => { setForm(EMPTY_FORM); setFormErrors({}); setFormOpen(true) }}>
                Create user
              </Button>
            }
          />
        </div>
        {users.isError ? (
          <div className="px-4 pb-4 sm:px-5 sm:pb-5">
            <ErrorState message={(users.error as Error)?.message} onRetry={() => users.refetch()} />
          </div>
        ) : (
          <>
            <DataTable
              rows={rows}
              columns={columns}
              rowKey={(row) => String(row.user_id)}
              loading={users.isFetching}
              emptyMessage="No users match this page"
            />
            <div className="px-4 pb-4 sm:px-5 sm:pb-5">
              <Pagination
                page={page}
                pageSize={pageSize}
                total={total}
                onPage={setPage}
                onPageSize={(size) => {
                  setPageSize(size)
                  setPage(1)
                }}
              />
            </div>
          </>
        )}
      </Card>

      {/* --------------------------------------------------------------- create user */}
      <Modal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        title="Create user"
        description="The account is active immediately and can sign in with this password."
        footer={
          <>
            <Button size="sm" variant="ghost" onClick={() => setFormOpen(false)}>
              Cancel
            </Button>
            <Button size="sm" variant="primary" loading={createUser.isPending} onClick={submit}>
              Create user
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Field label="Email" error={formErrors.email}>
            <TextInput
              type="email"
              autoComplete="off"
              placeholder="name@company.com"
              value={form.email}
              onChange={(event) => setForm((current) => ({ ...current, email: event.target.value }))}
            />
          </Field>

          <Field label="Full name" error={formErrors.fullName}>
            <TextInput
              placeholder="e.g. Ahmed Abobakr"
              value={form.fullName}
              onChange={(event) => setForm((current) => ({ ...current, fullName: event.target.value }))}
            />
          </Field>

          <Field
            label="Temporary password"
            error={formErrors.password}
            hint="At least 10 characters with an uppercase letter, a lowercase letter, a digit and a symbol."
          >
            <div className="relative">
              <TextInput
                type={showPassword ? 'text' : 'password'}
                autoComplete="new-password"
                className="pr-10"
                value={form.password}
                onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))}
              />
              <button
                type="button"
                onClick={() => setShowPassword((value) => !value)}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-subtle hover:bg-surface-3"
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </Field>

          <Field label="Role" error={formErrors.role}>
            <Select value={form.role} aria-label="Role" onChange={(event) => setForm((current) => ({ ...current, role: event.target.value }))}>
              {ROLES.map((role) => (
                <option key={role.id} value={role.id}>
                  {role.label}
                </option>
              ))}
            </Select>
          </Field>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Job title" hint="Optional">
              <TextInput
                placeholder="e.g. Data analyst"
                value={form.jobTitle}
                onChange={(event) => setForm((current) => ({ ...current, jobTitle: event.target.value }))}
              />
            </Field>
            <Field label="Department" hint="Optional">
              <TextInput
                placeholder="e.g. Commercial"
                value={form.department}
                onChange={(event) => setForm((current) => ({ ...current, department: event.target.value }))}
              />
            </Field>
          </div>
        </div>
      </Modal>

      {/* --------------------------------------------------------------- API keys drawer */}
      <Drawer open={Boolean(keysFor)} onClose={() => setKeysFor(null)} title={keysFor ? `API keys · ${keysFor.email}` : 'API keys'}>
        {keysFor ? (
          <div className="space-y-4">
            <KeyValue
              columns={1}
              items={[
                { label: 'User', value: keysFor.full_name },
                { label: 'Role', value: <Badge tone={roleTone(keysFor.role)}>{titleCase(keysFor.role)}</Badge> },
                { label: 'Account', value: keysFor.is_active ? 'Active' : 'Deactivated' },
              ]}
            />

            <Button size="sm" variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => setKeyFormOpen(true)}>
              Create API key
            </Button>

            {keys.isError ? (
              <ErrorState message={(keys.error as Error)?.message} onRetry={() => keys.refetch()} />
            ) : keys.isLoading ? (
              <LoadingState label="Loading keys…" rows={3} />
            ) : keys.data?.length ? (
              <ul className="space-y-2">
                {keys.data.map((key) => (
                  <li key={key.key_id} className="rounded-lg border border-line bg-surface-2 p-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-ink">{key.name}</p>
                        <p className="font-mono text-[11px] text-subtle">{key.prefix}………</p>
                      </div>
                      <Badge tone={key.is_active ? 'success' : 'neutral'}>{key.is_active ? 'Active' : 'Revoked'}</Badge>
                    </div>
                    <dl className="mt-2 grid grid-cols-2 gap-2 text-[11px]">
                      <div>
                        <dt className="text-subtle">Uses</dt>
                        <dd className="tabular-nums text-ink">{formatNumber(key.usage_count)}</dd>
                      </div>
                      <div>
                        <dt className="text-subtle">Last used</dt>
                        <dd className="text-ink" title={formatDateTime(key.last_used_at)}>
                          {formatRelative(key.last_used_at)}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-subtle">Created</dt>
                        <dd className="text-ink">{formatDateTime(key.created_at)}</dd>
                      </div>
                      <div>
                        <dt className="text-subtle">Expires</dt>
                        <dd className="text-ink">{key.expires_at ? formatDateTime(key.expires_at) : 'Never'}</dd>
                      </div>
                    </dl>
                    <div className="mt-2 flex justify-end">
                      <Button
                        size="sm"
                        variant="ghost"
                        icon={<Trash2 className="h-4 w-4 text-danger" />}
                        loading={revokeKey.isPending && revokeKey.variables?.keyId === key.key_id}
                        onClick={() => keyUserId !== null && revokeKey.mutate({ userId: keyUserId, keyId: key.key_id })}
                      >
                        Revoke
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState title="No API keys" message="Create a key to call the read-only API from a script." icon={<KeyRound className="h-6 w-6" />} />
            )}
          </div>
        ) : null}
      </Drawer>

      {/* --------------------------------------------------------------- create key */}
      <Modal
        open={keyFormOpen}
        onClose={() => setKeyFormOpen(false)}
        title="Create API key"
        description="Name the key so it can be recognised later."
        size="sm"
        footer={
          <>
            <Button size="sm" variant="ghost" onClick={() => setKeyFormOpen(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              variant="primary"
              loading={createKey.isPending}
              onClick={() => {
                if (keyName.trim().length < 2) {
                  setKeyNameError('Use at least 2 characters')
                  return
                }
                setKeyNameError(undefined)
                if (keyUserId !== null) createKey.mutate({ userId: keyUserId, name: keyName.trim() })
              }}
            >
              Create key
            </Button>
          </>
        }
      >
        <Field label="Key name" error={keyNameError} hint="e.g. Airflow scheduler">
          <TextInput value={keyName} placeholder="Reporting job" onChange={(event) => setKeyName(event.target.value)} />
        </Field>
      </Modal>

      {/* --------------------------------------------------------------- issued secret */}
      <Modal
        open={Boolean(issued)}
        onClose={() => setIssued(null)}
        title="API key created"
        description="Copy the key now — the full value is never shown again."
        footer={
          <Button size="sm" variant="primary" onClick={() => setIssued(null)}>
            I have stored it
          </Button>
        }
      >
        {issued ? (
          <div className="space-y-3">
            <div className="flex items-start gap-2 rounded-lg border border-warning/40 bg-warning-soft px-3 py-2.5">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden />
              <p className="text-xs text-ink">
                Only the prefix <span className="font-mono">{issued.prefix}</span> stays visible in the key list. If you lose the key,
                revoke it and create a new one.
              </p>
            </div>

            <div className="flex items-center gap-2 rounded-lg border border-line bg-surface-2 px-3 py-2">
              <code className="min-w-0 flex-1 break-all font-mono text-xs text-ink">{issued.api_key}</code>
              <IconButton label="Copy API key" icon={<Copy className="h-4 w-4" />} onClick={() => void copyIssuedKey()} />
            </div>

            <KeyValue
              columns={2}
              items={[
                { label: 'Name', value: issued.name },
                { label: 'Created', value: formatDateTime(issued.created_at) },
              ]}
            />
          </div>
        ) : null}
      </Modal>
    </div>
  )
}

/* ------------------------------------------------------------------------------------
   Labelled form field with inline validation message
   ------------------------------------------------------------------------------------ */
function Field({ label, hint, error, children }: { label: string; hint?: string; error?: string; children: ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-ink">{label}</label>
      {children}
      {error ? (
        <p className="mt-1 text-xs text-danger">{error}</p>
      ) : hint ? (
        <p className="mt-1 text-xs text-subtle">{hint}</p>
      ) : null}
    </div>
  )
}