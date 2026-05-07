import { useAuth } from '../auth/AuthContext'
import { Icon } from '../components/Icon'

export default function SettingsTab() {
  const { user, logout } = useAuth()
  const initials = (user?.name || user?.email || 'U')
    .split(/\s+/)
    .map(p => p[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()

  return (
    <div className="settings-block">
      <h3>Profile</h3>
      <p className="muted">Visible inside your workspace only.</p>
      <div className="card card-pad">
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
          {user?.picture ? (
            <img
              src={user.picture}
              alt={user.name}
              style={{ width: 48, height: 48, borderRadius: '50%', objectFit: 'cover' }}
            />
          ) : (
            <div className="user-avatar" style={{ width: 48, height: 48, fontSize: 16 }}>
              {initials}
            </div>
          )}
          <div>
            <div style={{ fontSize: 13, fontWeight: 600 }}>{user?.name || 'Unnamed'}</div>
            <div style={{ fontSize: 11, color: 'var(--fg-3)', marginTop: 2 }}>{user?.email}</div>
          </div>
        </div>
      </div>

      <h3 style={{ marginTop: 24, color: 'var(--c-neg)' }}>Danger zone</h3>
      <p className="muted">Sign out of this device.</p>
      <div style={{ display: 'flex', gap: 8 }}>
        <button className="btn btn-outline btn-sm" onClick={logout}>
          <Icon name="logout" /> Sign out
        </button>
      </div>
    </div>
  )
}
