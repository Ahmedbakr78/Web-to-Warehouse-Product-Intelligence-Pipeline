import { Component, type ErrorInfo, type ReactNode, lazy, Suspense } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'

import AppShell from './components/AppShell'
import { LoadingState } from './components/ui'
import { useAuth } from './hooks/useAuth'
import LoginPage from './pages/Login'

/* Route-level code splitting keeps the first paint small. */
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Analytics = lazy(() => import('./pages/Analytics'))
const Changes = lazy(() => import('./pages/Changes'))
const Products = lazy(() => import('./pages/Products'))
const ProductDetail = lazy(() => import('./pages/ProductDetail'))
const Categories = lazy(() => import('./pages/Categories'))
const Catalog = lazy(() => import('./pages/Catalog'))
const Pipeline = lazy(() => import('./pages/Pipeline'))
const Quality = lazy(() => import('./pages/Quality'))
const Sources = lazy(() => import('./pages/Sources'))
const QueryLab = lazy(() => import('./pages/QueryLab'))
const Builder = lazy(() => import('./pages/Builder'))
const Features = lazy(() => import('./pages/Features'))
const Forecast = lazy(() => import('./pages/Forecast'))
const Reports = lazy(() => import('./pages/Reports'))
const Alerts = lazy(() => import('./pages/Alerts'))
const Webhooks = lazy(() => import('./pages/Webhooks'))
const Account = lazy(() => import('./pages/Account'))
const Settings = lazy(() => import('./pages/Settings'))
const Users = lazy(() => import('./pages/Users'))
const Audit = lazy(() => import('./pages/Audit'))
const NotFound = lazy(() => import('./pages/NotFound'))

/* ------------------------------------------------------------------ error boundary */
class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled UI error', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-bg p-6 text-center">
          <h1 className="text-lg font-semibold text-ink">The dashboard hit an unexpected error</h1>
          <p className="max-w-lg text-sm text-muted">{this.state.error.message}</p>
          <div className="flex gap-2">
            <button className="btn btn-primary" onClick={() => this.setState({ error: null })}>
              Retry
            </button>
            <button className="btn btn-secondary" onClick={() => window.location.reload()}>
              Reload app
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

/* ------------------------------------------------------------------ route guards */
function RequireAuth({ children }: { children: ReactNode }) {
  const { authenticated, ready } = useAuth()
  const location = useLocation()
  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg">
        <LoadingState label="Restoring session…" rows={2} />
      </div>
    )
  }
  if (!authenticated) return <Navigate to="/login" state={{ from: location.pathname }} replace />
  return <>{children}</>
}

function RequirePermission({ permission, children }: { permission: string; children: ReactNode }) {
  const { can } = useAuth()
  if (!can(permission)) {
    return (
      <div className="card p-10 text-center">
        <p className="text-sm font-semibold text-ink">You do not have access to this screen</p>
        <p className="mt-1 text-xs text-muted">
          It requires the <code className="rounded bg-surface-3 px-1">{permission}</code> permission. Ask an
          administrator to upgrade your role.
        </p>
      </div>
    )
  }
  return <>{children}</>
}

/* ------------------------------------------------------------------ app */
export default function App() {
  return (
    <ErrorBoundary>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          element={
            <RequireAuth>
              <AppShell />
            </RequireAuth>
          }
        >
          <Route
            path="/"
            element={
              <Suspense fallback={<LoadingState label="Loading dashboard…" />}>
                <Dashboard />
              </Suspense>
            }
          />
          <Route
            path="/analytics"
            element={
              <Suspense fallback={<LoadingState label="Loading analytics…" />}>
                <Analytics />
              </Suspense>
            }
          />
          <Route
            path="/changes"
            element={
              <Suspense fallback={<LoadingState label="Loading change feed…" />}>
                <Changes />
              </Suspense>
            }
          />
          <Route
            path="/products"
            element={
              <Suspense fallback={<LoadingState label="Loading products…" />}>
                <Products />
              </Suspense>
            }
          />
          <Route
            path="/products/:id"
            element={
              <Suspense fallback={<LoadingState label="Loading product…" />}>
                <ProductDetail />
              </Suspense>
            }
          />
          <Route
            path="/categories"
            element={
              <Suspense fallback={<LoadingState label="Loading categories…" />}>
                <Categories />
              </Suspense>
            }
          />
          <Route
            path="/catalog"
            element={
              <Suspense fallback={<LoadingState label="Loading catalog…" />}>
                <Catalog />
              </Suspense>
            }
          />
          <Route
            path="/pipeline"
            element={
              <Suspense fallback={<LoadingState label="Loading pipeline…" />}>
                <Pipeline />
              </Suspense>
            }
          />
          <Route
            path="/quality"
            element={
              <Suspense fallback={<LoadingState label="Loading quality report…" />}>
                <Quality />
              </Suspense>
            }
          />
          <Route
            path="/sources"
            element={
              <Suspense fallback={<LoadingState label="Loading sources…" />}>
                <Sources />
              </Suspense>
            }
          />
          <Route
            path="/forecast"
            element={
              <Suspense fallback={<LoadingState label="Loading forecasting…" />}>
                <Forecast />
              </Suspense>
            }
          />
          <Route
            path="/reports"
            element={
              <Suspense fallback={<LoadingState label="Loading reports…" />}>
                <Reports />
              </Suspense>
            }
          />
          <Route
            path="/query"
            element={
              <RequirePermission permission="query">
                <Suspense fallback={<LoadingState label="Loading query lab…" />}>
                  <QueryLab />
                </Suspense>
              </RequirePermission>
            }
          />
          <Route
            path="/builder"
            element={
              <Suspense fallback={<LoadingState label="Loading builder…" />}>
                <Builder />
              </Suspense>
            }
          />
          <Route
            path="/features"
            element={
              <Suspense fallback={<LoadingState label="Loading feature catalogue…" />}>
                <Features />
              </Suspense>
            }
          />
          <Route
            path="/webhooks"
            element={
              <Suspense fallback={<LoadingState label="Loading webhooks…" />}>
                <Webhooks />
              </Suspense>
            }
          />
          <Route
            path="/alerts"
            element={
              <Suspense fallback={<LoadingState label="Loading alerts…" />}>
                <Alerts />
              </Suspense>
            }
          />
          <Route
            path="/account"
            element={
              <Suspense fallback={<LoadingState label="Loading account…" />}>
                <Account />
              </Suspense>
            }
          />
          <Route
            path="/settings"
            element={
              <RequirePermission permission="manage_settings">
                <Suspense fallback={<LoadingState label="Loading settings…" />}>
                  <Settings />
                </Suspense>
              </RequirePermission>
            }
          />
          <Route
            path="/users"
            element={
              <RequirePermission permission="manage_users">
                <Suspense fallback={<LoadingState label="Loading users…" />}>
                  <Users />
                </Suspense>
              </RequirePermission>
            }
          />
          <Route
            path="/audit"
            element={
              <RequirePermission permission="view_audit">
                <Suspense fallback={<LoadingState label="Loading audit trail…" />}>
                  <Audit />
                </Suspense>
              </RequirePermission>
            }
          />
          </Route>

        {/* 404 lives outside the auth guard: a signed-out visitor who mistypes a URL
            should see the not-found screen, not a login form. */}
        <Route
          path="*"
          element={
            <Suspense fallback={<LoadingState label="Loading…" />}>
              <NotFound />
            </Suspense>
          }
        />
      </Routes>
    </ErrorBoundary>
  )
}