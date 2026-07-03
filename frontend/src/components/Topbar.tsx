import { useCurrency } from '../context/CurrencyContext'
import { Icon } from './Icon'
import type { Route, ModalState } from '../App'

const TITLES: Record<Route, string> = {
  dashboard: 'Dashboard',
  sources: 'Sources',
  alerts: 'Alerts',
  settings: 'Settings',
}

interface Props {
  route: Route
  openModal: (m: ModalState) => void
  isDemo?: boolean
}

export default function Topbar({ route, openModal, isDemo }: Props) {
  const { currency, toggle, rate, lastUpdated } = useCurrency()

  return (
    <div className="topbar">
      <div>
        <div className="topbar-title">{TITLES[route]}</div>
      </div>
      <div className="topbar-meta">
        {lastUpdated && <span className="topbar-updated">Updated {lastUpdated}</span>}
        <div className="live-badge">
          <div className="live-dot"></div>
          LIVE
        </div>

        {/* Currency toggle */}
        <div style={{
          display: 'flex', background: 'var(--surf-2)', border: '1px solid var(--bdr)',
          borderRadius: 6, overflow: 'hidden',
        }}>
          {(['USD', 'TWD'] as const).map(c => (
            <div
              key={c}
              onClick={() => c !== currency && toggle()}
              style={{
                padding: '3px 9px', fontSize: 11, cursor: c !== currency ? 'pointer' : 'default',
                fontFamily: 'JetBrains Mono, monospace', fontWeight: currency === c ? 600 : 400,
                color: currency === c ? 'var(--accent)' : 'var(--fg-3)',
                background: currency === c ? 'var(--surf)' : 'transparent',
                userSelect: 'none',
              }}
            >
              {c}
            </div>
          ))}
        </div>

        <span className="topbar-rate mono">
          1 USD = {rate?.toFixed(2) ?? '--'} TWD
        </span>
        {!isDemo && (
          <button className="icon-btn" title="Refresh">
            <Icon name="refresh" />
          </button>
        )}
        <button
          className="btn btn-primary"
          data-tour="add-source-btn"
          onClick={() => openModal({ kind: 'addSource' })}
        >
          <Icon name="plus" />
          Add source
        </button>
      </div>
    </div>
  )
}
