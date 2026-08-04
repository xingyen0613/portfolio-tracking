import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useAuth } from '../auth/AuthContext'
import { useDemo } from '../context/DemoContext'
import { Icon } from '../components/Icon'
import GuideSection from '../components/GuideSection'
import LoginPromptModal from '../components/modals/LoginPromptModal'
import { cancelSubscription, redirectToEcpayCheckout, useEntitlement } from '../api/billing'

// 綠界信用卡收款服務審核中，正式金流未開通 → 訂閱入口停用、顯示「申請中」。
// 審核通過並完成正式環境測試後改為 false（取消訂閱按鈕不受此旗標影響）。
const CHECKOUT_PENDING = true

const STATUS_LABELS: Record<string, string> = {
  active: '訂閱中',
  trialing: '試用中',
  past_due: '扣款失敗（寬限中）',
  canceled: '已取消',
  none: '未訂閱',
  unenforced: '尚未開放訂閱',
}

function SubscriptionSection() {
  const queryClient = useQueryClient()
  const { isDemo } = useDemo()
  const { data: entitlement, isLoading } = useEntitlement()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showLogin, setShowLogin] = useState(false)

  // Demo mode has no token, so the entitlement query stays disabled — show the
  // plan itself (price + benefits) and send the visitor to login to subscribe.
  if (!isDemo && (isLoading || !entitlement)) return null

  const goSubscribe = async () => {
    setError(null)
    setBusy(true)
    try {
      await redirectToEcpayCheckout()
    } catch {
      setError('無法前往綠界付款頁，請稍後再試。')
    } finally {
      // Checkout opens in a new tab, so this page stays interactive.
      setBusy(false)
    }
  }

  const doCancel = async () => {
    if (!window.confirm('確定要取消訂閱？取消後不再自動扣款，已付的本期仍可使用到期。')) return
    setError(null)
    setBusy(true)
    try {
      await cancelSubscription()
      await queryClient.invalidateQueries({ queryKey: ['billing-status'] })
    } catch {
      setError('取消訂閱失敗，請稍後再試。')
    } finally {
      setBusy(false)
    }
  }

  const label = !entitlement
    ? STATUS_LABELS.none
    : entitlement.cancel_at_period_end && entitlement.active
      ? '已排程取消'
      : (STATUS_LABELS[entitlement.status] ?? entitlement.status)
  const periodEnd = entitlement?.current_period_end?.slice(0, 10)
  const canCancel =
    entitlement?.provider === 'ecpay' && entitlement.active && !entitlement.cancel_at_period_end
  const showSubscribe = !entitlement || (!entitlement.active && entitlement.status !== 'unenforced')

  return (
    <>
      <h3 style={{ marginTop: 24 }}>Subscription</h3>
      <p className="muted">訂閱後可新增來源並啟用每日自動同步。</p>
      <div className="card card-pad" data-tour="subscription">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 600 }}>{label}</div>
            {periodEnd && (
              <div style={{ fontSize: 11, color: 'var(--fg-3)', marginTop: 2 }}>
                {entitlement?.cancel_at_period_end ? '可用至' : '本期至'} {periodEnd}
              </div>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap' }}>
              NT$50
              <span style={{ fontSize: 11, fontWeight: 400, color: 'var(--fg-3)' }}> / 月</span>
            </div>
            {isDemo ? (
              // 預覽模式的按鈕只是叫出登入視窗，不會進金流，因此不受 CHECKOUT_PENDING 影響
              <button className="btn btn-primary btn-sm" onClick={() => setShowLogin(true)}>
                登入後訂閱
              </button>
            ) : CHECKOUT_PENDING && showSubscribe ? (
              <button className="btn btn-outline btn-sm" disabled title="金流服務審核中，尚無法訂閱">
                申請中
              </button>
            ) : showSubscribe ? (
              <button className="btn btn-primary btn-sm" onClick={goSubscribe} disabled={busy}>
                {busy ? '前往訂閱…' : '前往訂閱'}
              </button>
            ) : canCancel ? (
              <button className="btn btn-outline btn-sm" onClick={doCancel} disabled={busy}>
                {busy ? '處理中…' : '取消訂閱'}
              </button>
            ) : null}
          </div>
        </div>
        {error && (
          <div style={{ fontSize: 12, color: 'var(--c-neg)', marginTop: 8 }}>{error}</div>
        )}
        {!isDemo && CHECKOUT_PENDING && showSubscribe && (
          <div style={{ fontSize: 11, color: 'var(--fg-3)', marginTop: 8 }}>
            金流服務審核中，開通後即可訂閱。
          </div>
        )}
        <div style={{ borderTop: '1px solid var(--bdr)', marginTop: 14, paddingTop: 14 }}>
          <div style={{ fontSize: 12, color: 'var(--fg-2)', marginBottom: 6 }}>
            訂閱以獲得完整的網站功能，包括：
          </div>
          <ul style={{ margin: 0, paddingLeft: 18, listStyle: 'disc', fontSize: 12, color: 'var(--fg-3)', lineHeight: 1.8 }}>
            <li>每日自動跨平台紀錄資產變化</li>
            <li>細部持倉明細</li>
            <li>各項 benchmark 回測比較</li>
          </ul>
          <div style={{ fontSize: 11, color: 'var(--fg-3)', marginTop: 10 }}>
            可隨時取消，取消後不再扣款、本期可用至期末。詳見{' '}
            <a href="/refund" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent)' }}>
              退款政策
            </a>
            。
          </div>
        </div>
      </div>
      {showLogin && (
        <LoginPromptModal
          close={() => setShowLogin(false)}
          title="登入以訂閱"
          sub="使用 Google 帳號登入後即可開通訂閱"
        />
      )}
    </>
  )
}

export default function SettingsTab() {
  const { user, logout } = useAuth()
  const { isDemo } = useDemo()
  const initials = isDemo
    ? 'D'
    : (user?.name || user?.email || 'U')
        .split(/\s+/)
        .map(p => p[0])
        .slice(0, 2)
        .join('')
        .toUpperCase()

  return (
    <div className="settings-block">
      <h3>Profile</h3>
      <p className="muted">僅在您的工作區內可見。</p>
      <div className="card card-pad">
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
          {user?.picture && !isDemo ? (
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
            <div style={{ fontSize: 13, fontWeight: 600 }}>
              {isDemo ? '訪客（預覽模式）' : user?.name || '未命名'}
            </div>
            <div style={{ fontSize: 11, color: 'var(--fg-3)', marginTop: 2 }}>
              {isDemo ? '未登入 · 頁面資料均為範例' : user?.email}
            </div>
          </div>
        </div>
      </div>

      <SubscriptionSection />

      <GuideSection />

      <h3 style={{ marginTop: 24, color: 'var(--c-neg)' }}>Danger zone</h3>
      <p className="muted">登出此裝置。</p>
      <div style={{ display: 'flex', gap: 8 }}>
        <button className="btn btn-outline btn-sm" onClick={logout}>
          <Icon name="logout" /> 登出
        </button>
      </div>
    </div>
  )
}
