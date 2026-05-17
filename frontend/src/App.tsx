import { useEffect, useRef, useState } from 'react'
import { useAuth } from './auth/AuthContext'
import LoginPage from './pages/LoginPage'
import Sidebar from './components/Sidebar'
import Topbar from './components/Topbar'
import ModalHost from './components/modals/ModalHost'
import DashboardTab from './pages/DashboardTab'
import SourcesTab from './pages/SourcesTab'
import AlertsTab from './pages/AlertsTab'
import SettingsTab from './pages/SettingsTab'

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
  const [route, setRoute] = useState<Route>(() => {
    const saved = localStorage.getItem(ROUTE_KEY)
    return isRoute(saved) ? saved : 'dashboard'
  })
  const [modal, setModal] = useState<ModalState | null>(null)
  const prevTokenRef = useRef(token)

  useEffect(() => {
    if (prevTokenRef.current === null && token !== null) {
      setRoute('dashboard')
    }
    prevTokenRef.current = token
  }, [token])

  useEffect(() => {
    localStorage.setItem(ROUTE_KEY, route)
    window.scrollTo(0, 0)
  }, [route])

  if (!token) return <LoginPage />

  return (
    <div className="app">
      <Sidebar route={route} setRoute={setRoute} />
      <main className="main">
        <Topbar route={route} openModal={setModal} />
        <div className="page">
          {route === 'dashboard' && <DashboardTab openModal={setModal} />}
          {route === 'sources' && <SourcesTab openModal={setModal} />}
          {route === 'alerts' && <AlertsTab />}
          {route === 'settings' && <SettingsTab />}
        </div>
      </main>
      <ModalHost modal={modal} setModal={setModal} />
    </div>
  )
}
