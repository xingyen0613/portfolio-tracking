import { useAuth } from '../auth/AuthContext'
import { useDemo } from '../context/DemoContext'
import { Icon, type IconName } from './Icon'
import type { Route } from '../App'

interface NavItem {
  id: Route
  label: string
  icon: IconName
  disabled?: boolean
  badge?: string
}

const WORKSPACE: NavItem[] = [
  { id: 'dashboard', label: 'Dashboard', icon: 'trend' },
]

const MANAGE: NavItem[] = [
  { id: 'sources', label: 'Sources', icon: 'plug' },
  { id: 'alerts', label: 'Alerts', icon: 'bell', disabled: true, badge: 'Soon' },
  { id: 'settings', label: 'Settings', icon: 'settings' },
]

interface Props {
  route: Route
  setRoute: (r: Route) => void
}

export default function Sidebar({ route, setRoute }: Props) {
  const { user } = useAuth()
  const { isDemo, exitDemo } = useDemo()

  const renderItem = (it: NavItem) => (
    <div
      key={it.id}
      className={`nav-item ${route === it.id ? 'active' : ''}`}
      data-tour={it.id === 'sources' ? 'sidebar-sources' : undefined}
      style={it.disabled ? { opacity: 0.5, cursor: 'not-allowed' } : undefined}
      onClick={() => !it.disabled && setRoute(it.id)}
    >
      <Icon name={it.icon} />
      <span>{it.label}</span>
      {it.badge && <span className="nav-badge">{it.badge}</span>}
    </div>
  )

  const initials = (user?.name || user?.email || 'AC')
    .split(/\s+/)
    .map(p => p[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()

  return (
    <aside className="sidebar">
      <div className="brand">
        <div>
          <div className="brand-name">ALL IN</div>
          <div className="brand-sub">Portfolio tracker</div>
        </div>
      </div>

      <div className="nav-section">
        <div className="nav-label">Workspace</div>
        {WORKSPACE.map(renderItem)}
      </div>

      <div className="nav-section">
        <div className="nav-label">Manage</div>
        {MANAGE.map(renderItem)}
      </div>

      {isDemo ? (
        <div className="user-card" onClick={exitDemo} title="退出展示模式">
          <div className="user-avatar" style={{ background: 'rgba(124,110,245,0.25)', color: 'var(--accent)', fontSize: 13, fontWeight: 700 }}>
            D
          </div>
          <div className="user-meta">
            <div className="user-name" style={{ color: 'var(--accent)' }}>展示模式</div>
            <div className="user-plan">點此退出展示</div>
          </div>
          <Icon name="chevronR" className="user-chev" />
        </div>
      ) : (
        <div className="user-card" onClick={() => setRoute('settings')}>
          {user?.picture ? (
            <img
              src={user.picture}
              alt={user.name}
              style={{ width: 30, height: 30, borderRadius: '50%', objectFit: 'cover' }}
            />
          ) : (
            <div className="user-avatar">{initials}</div>
          )}
          <div className="user-meta">
            <div className="user-name">{user?.name || user?.email || '使用者'}</div>
            <div className="user-plan">管理帳戶</div>
          </div>
          <Icon name="chevronR" className="user-chev" />
        </div>
      )}
    </aside>
  )
}
