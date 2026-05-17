import { useCallback, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useAuth } from './auth/AuthContext'
import LoginPage from './pages/LoginPage'
import Sidebar from './components/Sidebar'
import Topbar from './components/Topbar'
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
  const { token } = useAuth()
  const qc = useQueryClient()
  const [route, setRoute] = useState<Route>(() => {
    const saved = localStorage.getItem(ROUTE_KEY)
    return isRoute(saved) ? saved : 'dashboard'
  })
  const [modal, setModal] = useState<ModalState | null>(null)
  const [importToast, setImportToast] = useState<ImportHistoryResult | null>(null)
  const prevTokenRef = useRef(token)
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

  useEffect(() => {
    localStorage.setItem(ROUTE_KEY, route)
    if (mainRef.current) mainRef.current.scrollTop = 0
  }, [route])

  if (!token) return <LoginPage />

  return (
    <div className="app">
      <Sidebar route={route} setRoute={setRoute} />
      <main className="main" ref={mainRef}>
        <Topbar route={route} openModal={setModal} />
        <div className="page">
          {route === 'dashboard' && <DashboardTab openModal={setModal} />}
          {route === 'sources' && <SourcesTab openModal={setModal} />}
          {route === 'alerts' && <AlertsTab />}
          {route === 'settings' && <SettingsTab />}
        </div>
      </main>
      <ModalHost modal={modal} setModal={setModal} />
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
  )
}
