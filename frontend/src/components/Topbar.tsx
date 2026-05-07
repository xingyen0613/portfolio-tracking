import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { Icon } from './Icon'
import type { Route, ModalState } from '../App'

interface MetaData {
  last_updated: string | null
  usd_twd_rate: number
}

const TITLES: Record<Route, string> = {
  dashboard: 'Dashboard',
  sources: 'Sources',
  alerts: 'Alerts',
  settings: 'Settings',
}

interface Props {
  route: Route
  openModal: (m: ModalState) => void
}

export default function Topbar({ route, openModal }: Props) {
  const { data: meta } = useQuery<MetaData>({
    queryKey: ['portfolio/meta'],
    queryFn: () => api.get('/api/portfolio/meta').then(r => r.data),
    staleTime: 5 * 60 * 1000,
  })

  return (
    <div className="topbar">
      <div>
        <div className="topbar-title">{TITLES[route]}</div>
      </div>
      <div className="topbar-meta">
        {meta?.last_updated && <span>Updated {meta.last_updated}</span>}
        <div className="live-badge">
          <div className="live-dot"></div>
          LIVE
        </div>
        <span className="topbar-rate mono">
          1 USD = {meta?.usd_twd_rate?.toFixed(2) ?? '--'} TWD
        </span>
        <button className="icon-btn" title="Refresh">
          <Icon name="refresh" />
        </button>
        <button
          className="btn btn-primary"
          onClick={() => openModal({ kind: 'addSource' })}
        >
          <Icon name="plus" />
          Add source
        </button>
      </div>
    </div>
  )
}
