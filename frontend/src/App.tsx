import { useCallback, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useAuth } from './auth/AuthContext'
import { CurrencyProvider } from './context/CurrencyContext'
import { DemoProvider, useDemo } from './context/DemoContext'
import LoginPage from './pages/LoginPage'
import LegalPage from './pages/LegalPage'
import { legalSlugForPath } from './legal/content'
import Sidebar from './components/Sidebar'
import Topbar from './components/Topbar'
import Footer from './components/Footer'
import DemoBanner from './components/DemoBanner'
import DemoTour from './components/DemoTour'
import ModalHost from './components/modals/ModalHost'
import DashboardTab from './pages/DashboardTab'
import SourcesTab from './pages/SourcesTab'
import AlertsTab from './pages/AlertsTab'
import SettingsTab from './pages/SettingsTab'
import { type ImportHistoryResult } from './api/connectors'
import { IMPORT_HISTORY_MUTATION_KEY } from './components/modals/ImportHistoryModal'

export type Route = 'dashboard' | 'sources' | 'alerts' | 'settings'

export type ModalState =
  | { kind: 'addSource' }
  | { kind: 'connect'; templateId: string }
  | { kind: 'editSource'; connectorId: string }
  | { kind: 'importHistory'; connector: import('./api/connectors').Connector }

const ROUTE_KEY = 'pt_route'

function isRoute(v: unknown): v is Route {
  return v === 'dashboard' || v === 'sources' || v === 'alerts' || v === 'settings'
}

export default function App() {
  // Legal pages live at their own URLs and need no auth.
  const legalSlug = legalSlugForPath(window.location.pathname)
  if (legalSlug) return <LegalPage slug={legalSlug} />

  return (
    <DemoProvider>
      <AppInner />
    </DemoProvider>
  )
}

function AppInner() {
  const { token } = useAuth()
  const { isDemo } = useDemo()
  const qc = useQueryClient()
  const [route, setRoute] = useState<Route>(() => {
    const saved = localStorage.getItem(ROUTE_KEY)
    return isRoute(saved) ? saved : 'dashboard'
  })
  const [modal, setModal] = useState<ModalState | null>(null)
  const [importToast, setImportToast] = useState<ImportHistoryResult | null>(null)
  const [oauthToast, setOauthToast] = useState<{ ok: boolean; msg: string } | null>(null)
  const [yuantaFetchingUntil, setYuantaFetchingUntil] = useState<number | null>(null)
  const prevTokenRef = useRef(token)
  const prevDemoRef = useRef(isDemo)
  const mainRef = useRef<HTMLElement>(null)

  const handleImportDone = useCallback((result: ImportHistoryResult) => {
    qc.invalidateQueries({
      predicate: q => typeof q.queryKey[0] === 'string' && q.queryKey[0].startsWith('portfolio'),
    })
    setImportToast(result)
    setTimeout(() => setImportToast(null), 6000)
  }, [qc])

  // MutationCache subscription — fires even when ImportHistoryModal is unmounted
  useEffect(() => {
    return qc.getMutationCache().subscribe((event) => {
      if (
        event.type === 'updated' &&
        event.mutation?.options.mutationKey?.[0] === IMPORT_HISTORY_MUTATION_KEY &&
        event.mutation.state.status === 'success'
      ) {
        handleImportDone(event.mutation.state.data as ImportHistoryResult)
      }
    })
  }, [qc, handleImportDone])

  useEffect(() => {
    if (prevTokenRef.current === null && token !== null) {
      setRoute('dashboard')
    }
    prevTokenRef.current = token
  }, [token])

  // Entering demo → land on dashboard so the tour targets exist
  useEffect(() => {
    if (!prevDemoRef.current && isDemo) {
      setRoute('dashboard')
    }
    prevDemoRef.current = isDemo
  }, [isDemo])

  // Detect OAuth callback (e.g. ?oauth=yuanta_success after Gmail redirect)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const oauth = params.get('oauth')
    if (!oauth) return
    window.history.replaceState({}, '', window.location.pathname)
    if (oauth === 'yuanta_success') {
      qc.invalidateQueries({ queryKey: ['connectors'] })
      setOauthToast({ ok: true, msg: '元大證券已連接，首次同步在背景執行中。' })
      setTimeout(() => setOauthToast(null), 6000)
      // Show Fetching state in SourcesTab for 90s while background batch runs
      const until = Date.now() + 90000
      setYuantaFetchingUntil(until)
      const interval = setInterval(() => {
        qc.invalidateQueries({ queryKey: ['connectors'] })
      }, 5000)
      setTimeout(() => {
        clearInterval(interval)
        setYuantaFetchingUntil(null)
      }, 90000)
    } else if (oauth.startsWith('yuanta_error')) {
      const reason = params.get('reason') ?? 'unknown'
      setOauthToast({ ok: false, msg: `元大 Gmail 授權失敗：${reason}` })
      setTimeout(() => setOauthToast(null), 8000)
    }
  }, [qc])

  useEffect(() => {
    localStorage.setItem(ROUTE_KEY, route)
    if (mainRef.current) mainRef.current.scrollTop = 0
  }, [route])

  if (!token && !isDemo) return <LoginPage />

  return (
    <CurrencyProvider>
    <div className="app">
      <Sidebar route={route} setRoute={setRoute} />
      <main className="main" ref={mainRef}>
        {isDemo && <DemoBanner />}
        <Topbar route={route} openModal={setModal} isDemo={isDemo} />
        <div className="page">
          {route === 'dashboard' && <DashboardTab openModal={setModal} />}
          {route === 'sources' && <SourcesTab openModal={setModal} yuantaFetchingUntil={yuantaFetchingUntil} />}
          {route === 'alerts' && <AlertsTab />}
          {route === 'settings' && <SettingsTab />}
        </div>
        <Footer />
      </main>
      <ModalHost modal={modal} setModal={setModal} />
      {isDemo && <DemoTour />}
      {oauthToast && (
        <div style={{
          position: 'fixed', bottom: 24, right: 24, zIndex: 9999,
          background: 'var(--surf-1)',
          border: `1px solid ${oauthToast.ok ? 'rgba(46,184,138,0.4)' : 'rgba(236,91,126,0.4)'}`,
          borderRadius: 12, padding: '14px 16px',
          boxShadow: '0 4px 24px rgba(0,0,0,0.35)',
          display: 'flex', alignItems: 'flex-start', gap: 12, minWidth: 240, maxWidth: 340,
        }}>
          <div style={{
            width: 8, height: 8, borderRadius: '50%',
            background: oauthToast.ok ? 'var(--c-pos)' : 'var(--c-neg)',
            flexShrink: 0, marginTop: 5,
          }} />
          <div style={{ flex: 1, fontSize: 13, color: 'var(--fg)', lineHeight: 1.5 }}>
            {oauthToast.msg}
          </div>
          <button
            onClick={() => setOauthToast(null)}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: 'var(--fg-3)', fontSize: 16, lineHeight: 1, padding: 0, flexShrink: 0,
            }}
          >
            ×
          </button>
        </div>
      )}
      {importToast && (
        <div style={{
          position: 'fixed', bottom: 24, right: 24, zIndex: 9999,
          background: 'var(--surf-1)',
          border: '1px solid rgba(46,184,138,0.4)',
          borderRadius: 12, padding: '14px 16px',
          boxShadow: '0 4px 24px rgba(0,0,0,0.35)',
          display: 'flex', alignItems: 'flex-start', gap: 12, minWidth: 240, maxWidth: 320,
        }}>
          <div style={{
            width: 8, height: 8, borderRadius: '50%',
            background: 'var(--c-pos)', flexShrink: 0, marginTop: 5,
          }} />
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--fg)', marginBottom: 2 }}>
              Import complete
            </div>
            <div style={{ fontSize: 12, color: 'var(--fg-2)' }}>
              {importToast.written_count} {importToast.written_count === 1 ? 'row' : 'rows'} written
              {importToast.date_from && importToast.date_to && (
                <> · {importToast.date_from} → {importToast.date_to}</>
              )}
            </div>
          </div>
          <button
            onClick={() => setImportToast(null)}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: 'var(--fg-3)', fontSize: 16, lineHeight: 1, padding: 0, flexShrink: 0,
            }}
          >
            ×
          </button>
        </div>
      )}
    </div>
    </CurrencyProvider>
  )
}
