/**
 * Two-factor authentication and signed-in devices, for the Account screen.
 *
 * Enrolment is deliberately two-step and mirrors the server: `/2fa/setup` returns a
 * secret exactly once, and nothing is enabled until `/2fa/activate` accepts a real
 * code. That ordering means a mistyped secret cannot lock the user out of their own
 * account, which is the usual failure mode of 2FA enrolment flows.
 */

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Check,
  Copy,
  Fingerprint,

  Laptop,
  LogOut,
  RefreshCw,
  ShieldCheck,
  ShieldQuestion,
  Smartphone,
  TriangleAlert,
} from 'lucide-react'

import {
  Badge,
  Button,
  Card,
  CardHeader,
  DataTable,
  KeyValue,
  LoadingState,
  Modal,
  TextInput,
  useToast,
} from '@/components/ui'
import { endpoints } from '@/lib/api'
import { useApiQuery } from '@/hooks/useApi'
import { cn } from '@/lib/cn'
import { formatDateTime, formatRelative } from '@/lib/format'

export default function SecurityPanel() {
  const toast = useToast()
  const queryClient = useQueryClient()

  const status = useApiQuery(['two-factor-status'], endpoints.twoFactorStatus, { staleTime: 60_000 })
  const sessions = useApiQuery(['sessions'], () => endpoints.sessions(localStorage.getItem('pip.session') ?? undefined), {
    staleTime: 30_000,
  })

  const [setupOpen, setSetupOpen] = useState(false)
  const [secret, setSecret] = useState<string>('')
  const [uri, setUri] = useState<string>('')
  const [code, setCode] = useState('')
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null)
  const [disableOpen, setDisableOpen] = useState(false)
  const [disableCode, setDisableCode] = useState('')

  const setup = useMutation({
    mutationFn: endpoints.twoFactorSetup,
    onSuccess: (payload) => {
      setSecret(String(payload.secret))
      setUri(String(payload.otpauth_uri))
      setCode('')
      setSetupOpen(true)
    },
    onError: (error) => toast.error('Could not start enrolment', (error as Error).message),
  })

  const activate = useMutation({
    mutationFn: () => endpoints.twoFactorActivate(secret, code),
    onSuccess: (payload) => {
      setSetupOpen(false)
      setRecoveryCodes(payload.recovery_codes ?? [])
      void queryClient.invalidateQueries({ queryKey: ['two-factor-status'] })
      toast.success('Two-factor authentication enabled', 'Store the recovery codes now')
    },
    onError: (error) => toast.error('That code was not accepted', (error as Error).message),
  })

  const disable = useMutation({
    mutationFn: () => endpoints.twoFactorDisable(disableCode),
    onSuccess: () => {
      setDisableOpen(false)
      setDisableCode('')
      void queryClient.invalidateQueries({ queryKey: ['two-factor-status'] })
      toast.success('Two-factor authentication disabled')
    },
    onError: (error) => toast.error('Could not disable it', (error as Error).message),
  })

  const revoke = useMutation({
    mutationFn: (key: string) => endpoints.revokeSession(key),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['sessions'] })
      toast.success('Device signed out')
    },
    onError: (error) => toast.error('Could not sign that device out', (error as Error).message),
  })

  const revokeOthers = useMutation({
    mutationFn: () => {
      const current = localStorage.getItem('pip.session')
      if (!current) throw new Error('No session handle for this browser')
      return endpoints.revokeOtherSessions(current)
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['sessions'] })
      toast.success('Signed out of every other device')
    },
    onError: (error) => toast.error('Could not sign the others out', (error as Error).message),
  })

  const enabled = Boolean(status.data?.enabled)
  const attemptsLeft = Number(status.data?.attempts_remaining ?? 3)

  return (
    <>
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        {/* ------------------------------------------------------- two-factor */}
        <Card>
          <CardHeader
            title="Two-factor authentication"
            subtitle="A six-digit code from your authenticator app, on every sign-in"
            icon={enabled ? <ShieldCheck className="h-4 w-4" /> : <ShieldQuestion className="h-4 w-4" />}
          />

          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={enabled ? 'success' : 'warning'}>{enabled ? 'Enabled' : 'Not enabled'}</Badge>
            {status.data?.enrolled_at ? (
              <span className="text-[11px] text-subtle">since {formatDateTime(status.data.enrolled_at)}</span>
            ) : null}
            {status.data?.locked ? (
              <Badge tone="danger">Locked after repeated failures</Badge>
            ) : enabled && attemptsLeft <= 1 ? (
              <Badge tone="warning">{attemptsLeft} attempt(s) left</Badge>
            ) : null}
          </div>

          {enabled ? (
            <div className="mt-4 space-y-3">
              <KeyValue
                items={[
                  {
                    label: 'Recovery codes left',
                    value: (
                      <span className={cn((status.data?.recovery_codes_remaining ?? 0) <= 2 && 'text-danger')}>
                        {status.data?.recovery_codes_remaining ?? 0} of 8
                      </span>
                    ),
                  },
                  { label: 'Method', value: 'TOTP · SHA-1 · 30 s step' },
                ]}
              />
              {(status.data?.recovery_codes_remaining ?? 0) <= 2 ? (
                <p className="flex items-start gap-2 rounded-lg bg-danger-soft p-3 text-[11px] leading-relaxed text-muted">
                  <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-danger" aria-hidden />
                  <span>
                    You are running low on recovery codes. Generate a fresh set, or a lost device will end in a
                    password reset.
                  </span>
                </p>
              ) : null}
              <div className="flex flex-wrap gap-2">
                <Button variant="danger" icon={<ShieldQuestion className="h-4 w-4" />} onClick={() => setDisableOpen(true)}>
                  Turn off
                </Button>
              </div>
            </div>
          ) : (
            <div className="mt-4 space-y-3">
              <p className="text-xs leading-relaxed text-muted">
                Add a second factor so a stolen password is not enough to sign in. You will need an authenticator
                app: Google Authenticator, Authy, 1Password or any TOTP-compatible app.
              </p>
              <Button
                variant="primary"
                icon={<Fingerprint className="h-4 w-4" />}
                loading={setup.isPending}
                onClick={() => setup.mutate()}
              >
                Set up two-factor
              </Button>
            </div>
          )}

          {enabled ? (
            <p className="mt-4 rounded-lg bg-surface-2 p-3 text-[11px] leading-relaxed text-muted">
              Three wrong codes lock the second factor for five minutes, so a stolen password cannot be brute-forced
              through it. A recovery code is still accepted while locked, because it is proof of possession in its own
              right — otherwise three mistyped codes would leave you locked out.
            </p>
          ) : null}
        </Card>

        {/* ---------------------------------------------------------- sessions */}
        <Card padded={false}>
          <div className="flex flex-wrap items-start justify-between gap-3 p-4 sm:p-5">
            <CardHeader
              title="Signed-in devices"
              subtitle="Revoke any session you do not recognise"
              icon={<Laptop className="h-4 w-4" />}
            />
            <Button
              size="sm"
              variant="secondary"
              icon={<LogOut className="h-4 w-4" />}
              loading={revokeOthers.isPending}
              onClick={() => revokeOthers.mutate()}
            >
              Sign out everywhere else
            </Button>
          </div>

          {sessions.isLoading ? (
            <div className="p-6">
              <LoadingState label="Loading your devices…" rows={2} />
            </div>
          ) : sessions.data?.sessions?.length ? (
            <DataTable
              rows={sessions.data.sessions as any[]}
              rowKey={(row: any) => row.session_key}
              maxHeight={340}
              columns={[
                {
                  key: 'device',
                  header: 'Device',
                  render: (row: any) => (
                    <div className="flex items-center gap-2">
                      <Smartphone className="h-4 w-4 shrink-0 text-subtle" aria-hidden />
                      <div className="min-w-0">
                        <p className="truncate font-medium">{row.device ?? 'Unknown device'}</p>
                        <p className="truncate text-[11px] text-subtle">{row.ip_address ?? 'unknown address'}</p>
                      </div>
                    </div>
                  ),
                },
                {
                  key: 'created_at',
                  header: 'Signed in',
                  render: (row: any) => (
                    <span title={formatDateTime(row.created_at)}>{formatRelative(row.created_at)}</span>
                  ),
                },
                {
                  key: 'last_seen_at',
                  header: 'Last seen',
                  render: (row: any) => (row.last_seen_at ? formatRelative(row.last_seen_at) : '—'),
                },
                {
                  key: 'state',
                  header: 'State',
                  render: (row: any) => (
                    <div className="flex flex-wrap items-center gap-1">
                      {row.is_current ? <Badge tone="success">This device</Badge> : null}
                      {row.is_active ? (
                        <Badge tone="neutral">active</Badge>
                      ) : (
                        <Badge tone="danger">{row.revoked_reason ?? 'expired'}</Badge>
                      )}
                    </div>
                  ),
                },
                {
                  key: 'actions',
                  header: '',
                  align: 'right',
                  render: (row: any) =>
                    row.is_current || !row.is_active ? null : (
                      <Button
                        size="sm"
                        variant="ghost"
                        icon={<LogOut className="h-3.5 w-3.5" />}
                        onClick={() => revoke.mutate(row.session_key)}
                        disabled={revoke.isPending}
                      >
                        Revoke
                      </Button>
                    ),
                },
              ]}
            />
          ) : (
            <div className="p-6 text-center text-xs text-subtle">No other sessions recorded.</div>
          )}
        </Card>
      </div>

      {/* ------------------------------------------------------- setup modal */}
      <Modal
        open={setupOpen}
        onClose={() => setSetupOpen(false)}
        title="Set up two-factor authentication"
        description="Step 1 of 2: add the key to your app, then confirm it works."
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => setSetupOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              icon={<Check className="h-4 w-4" />}
              loading={activate.isPending}
              disabled={code.length !== 6}
              onClick={() => activate.mutate()}
            >
              Confirm and enable
            </Button>
          </>
        }
      >
        <ol className="space-y-4">
          <li>
            <p className="stat-label mb-1.5">1. Add the key to your authenticator</p>
            <p className="mb-2 text-xs text-muted">
              Scan the QR code with your app, or type the secret in by hand.
            </p>
            <div className="rounded-lg bg-surface-2 p-3">
              {uri ? (
                <img
                  src={`https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(uri)}`}
                  alt="Two-factor enrolment QR code"
                  className="mx-auto rounded bg-white p-2"
                  width={180}
                  height={180}
                />
              ) : null}
              <p className="mt-2 break-all text-center font-mono text-[11px] text-muted">{secret}</p>
              <Button
                size="sm"
                variant="ghost"
                icon={<Copy className="h-3.5 w-3.5" />}
                className="mt-1"
                onClick={() =>
                  navigator.clipboard?.writeText(secret).then(
                    () => toast.success('Secret copied'),
                    () => toast.error('Clipboard unavailable'),
                  )
                }
              >
                Copy secret
              </Button>
            </div>
          </li>
          <li>
            <p className="stat-label mb-1.5">2. Enter the code your app shows</p>
            <TextInput
              value={code}
              onChange={(event) => setCode(event.target.value.replace(/\D/g, '').slice(0, 6))}
              inputMode="numeric"
              autoComplete="one-time-code"
              placeholder="000000"
              className="font-mono text-lg tracking-[0.3em]"
            />
            <p className="mt-1.5 text-[11px] text-subtle">
              Nothing is enabled until this matches. If your device clock has drifted, syncing it fixes the code.
            </p>
          </li>
        </ol>
      </Modal>

      {/* --------------------------------------------------- recovery modal */}
      <Modal
        open={recoveryCodes !== null}
        onClose={() => setRecoveryCodes(null)}
        title="Save your recovery codes"
        description="This is the only time they are shown. Each one works once."
        size="lg"
        footer={
          <Button
            variant="primary"
            onClick={() => {
              if (recoveryCodes) {
                navigator.clipboard?.writeText(recoveryCodes.join('\n')).then(
                  () => toast.success('Recovery codes copied'),
                  () => toast.error('Clipboard unavailable'),
                )
              }
            }}
            icon={<Copy className="h-4 w-4" />}
          >
            Copy all
          </Button>
        }
      >
        <p className="mb-3 text-xs text-muted">
          Store them somewhere other than the device that holds the authenticator — a password manager, or a printed
          copy in a safe place. They are stored hashed, so nobody can read them back out of the database.
        </p>
        <ul className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {(recoveryCodes ?? []).map((item) => (
            <li key={item} className="rounded-lg bg-surface-2 px-2 py-1.5 text-center font-mono text-xs">
              {item}
            </li>
          ))}
        </ul>
        <p className="mt-3 flex items-start gap-2 text-[11px] text-subtle">
          <RefreshCw className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
          Regenerating later invalidates these.
        </p>
      </Modal>

      {/* ----------------------------------------------------- disable modal */}
      <Modal
        open={disableOpen}
        onClose={() => setDisableOpen(false)}
        title="Turn off two-factor authentication"
        description="Confirm with a current code. Your password alone will not do."
        footer={
          <>
            <Button variant="secondary" onClick={() => setDisableOpen(false)}>
              Keep it on
            </Button>
            <Button
              variant="danger"
              loading={disable.isPending}
              disabled={disableCode.length !== 6}
              onClick={() => disable.mutate()}
            >
              Turn off
            </Button>
          </>
        }
      >
        <TextInput
          value={disableCode}
          onChange={(event) => setDisableCode(event.target.value.replace(/\D/g, '').slice(0, 6))}
          inputMode="numeric"
          autoComplete="one-time-code"
          placeholder="000000"
          className="font-mono text-lg tracking-[0.3em]"
        />
      </Modal>
    </>
  )
}