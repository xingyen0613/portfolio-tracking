import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { Icon } from '../components/Icon'
import { createCheckoutSession, createPortalSession, useEntitlement } from '../api/billing'

const STATUS_LABELS: Record<string, string> = {
  active: '訂閱中',
  trialing: '試用中',
  past_due: '扣款失敗（寬限中）',
  canceled: '已取消',
  none: '未訂閱',
  unenforced: '未啟用收費',
}

function SubscriptionSection() {
  const { data: entitlement, isLoading } = useEntitlement()
  const [redirecting, setRedirecting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (isLoading || !entitlement) return null

  const goTo = async (fn: () => Promise<{ url: string }>) => {
    setError(null)
    setRedirecting(true)
    try {
      const { url } = await fn()
      window.location.href = url
    } catch {
      setError('無法開啟頁面，請稍後再試。')
      setRedirecting(false)
    }
  }

  const label = STATUS_LABELS[entitlement.status] ?? entitlement.status
  const periodEnd = entitlement.current_period_end?.slice(0, 10)
  const canManage = entitlement.provider === 'stripe'
  const showSubscribe = !entitlement.active && entitlement.status !== 'unenforced'

  return (
    <>
      <h3 style={{ marginTop: 24 }}>Subscription</h3>
      <p className="muted">Unlocks adding sources and daily auto-sync.</p>
      <div className="card card-pad">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 600 }}>{label}</div>
            {periodEnd && (
              <div style={{ fontSize: 11, color: 'var(--fg-3)', marginTop: 2 }}>
                {entitlement.status === 'canceled' ? '原可用至' : '本期至'} {periodEnd}
              </div>
            )}
          </div>
          {showSubscribe ? (
            <button
              className="btn btn-primary btn-sm"
              onClick={() => goTo(createCheckoutSession)}
              disabled={redirecting}
            >
              {redirecting ? '前往訂閱…' : '前往訂閱'}
            </button>
          ) : canManage ? (
            <button
              className="btn btn-outline btn-sm"
              onClick={() => goTo(createPortalSession)}
              disabled={redirecting}
            >
              {redirecting ? '開啟中…' : '管理訂閱'}
            </button>
          ) : null}
        </div>
        {error && (
          <div style={{ fontSize: 12, color: 'var(--c-neg)', marginTop: 8 }}>{error}</div>
        )}
      </div>
    </>
  )
}

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

      <SubscriptionSection />

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
