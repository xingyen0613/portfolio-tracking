import { useState } from 'react'
import axios from 'axios'
import { GoogleLogin } from '@react-oauth/google'
import { useAuth } from '../auth/AuthContext'
import { useDemo } from '../context/DemoContext'
import Footer from '../components/Footer'

export default function LoginPage() {
  const { login } = useAuth()
  const { enterDemo } = useDemo()
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleLogin(credential: string) {
    setLoading(true)
    setError(null)
    try {
      await login(credential)
    } catch (e: unknown) {
      const detail = axios.isAxiosError(e)
        ? e.response?.data?.detail ?? `${e.message}（HTTP ${e.response?.status ?? 'n/a'}）`
        : e instanceof Error ? e.message : String(e)
      setError(`登入失敗：${detail}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-mobile-stage">
      <div className="phone-frame">
        <div className="phone-notch"></div>
        <div className="phone-screen">
          <div className="m-brand">
            <div className="m-brand-mark"></div>
            <div className="m-brand-name">ALL IN</div>
            <div className="m-brand-sub">Portfolio tracker</div>
          </div>

          <div
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'center',
              alignItems: 'center',
              textAlign: 'center',
              padding: '0 4px',
            }}
          >
            <div className="m-headline" style={{ marginBottom: 8 }}>
              All Accounts,
              <br />
              All In One.
            </div>
            <div className="m-sub" style={{ marginBottom: 32 }}>
              連接交易所、錢包與券商，在專屬儀表板一次掌握完整資產。
            </div>

            {loading ? (
              <span style={{ color: 'var(--fg-3)', fontSize: 13 }}>驗證中⋯</span>
            ) : (
              <GoogleLogin
                onSuccess={(res) => {
                  if (res.credential) handleLogin(res.credential)
                }}
                onError={() => setError('Google 登入失敗，請再試一次')}
                theme="filled_black"
                shape="pill"
                text="signin_with"
                size="large"
                width="240"
              />
            )}

            {error && (
              <div
                style={{
                  marginTop: 16,
                  color: 'var(--c-neg)',
                  fontSize: 12,
                  background: 'rgba(236,91,126,0.08)',
                  border: '1px solid rgba(236,91,126,0.3)',
                  borderRadius: 8,
                  padding: '8px 12px',
                  maxWidth: 280,
                  textAlign: 'center',
                }}
              >
                {error}
              </div>
            )}

            <div style={{ margin: '16px 0 4px', display: 'flex', alignItems: 'center', gap: 10, width: 240 }}>
              <div style={{ flex: 1, height: 1, background: 'var(--bdr)' }} />
              <span style={{ fontSize: 11, color: 'var(--fg-3)' }}>或</span>
              <div style={{ flex: 1, height: 1, background: 'var(--bdr)' }} />
            </div>

            <button
              onClick={enterDemo}
              style={{
                width: 240,
                padding: '9px 0',
                background: 'transparent',
                border: '1px solid var(--bdr)',
                borderRadius: 20,
                color: 'var(--fg-2)',
                fontSize: 13,
                fontWeight: 500,
                cursor: 'pointer',
                transition: 'all 150ms',
                letterSpacing: '0.01em',
              }}
              onMouseEnter={e => {
                e.currentTarget.style.borderColor = 'var(--bdr-strong)'
                e.currentTarget.style.color = 'var(--fg)'
                e.currentTarget.style.background = 'var(--surf-2)'
              }}
              onMouseLeave={e => {
                e.currentTarget.style.borderColor = 'var(--bdr)'
                e.currentTarget.style.color = 'var(--fg-2)'
                e.currentTarget.style.background = 'transparent'
              }}
            >
              預覽模式（免登入）
            </button>

            <div
              className="m-foot"
              style={{
                marginTop: 18,
                fontSize: 11,
                color: 'var(--fg-3)',
                lineHeight: 1.5,
              }}
            >
              繼續即代表您同意我們的
              <br />
              <a className="legal-inline-link" href="/terms" target="_blank" rel="noopener noreferrer">
                服務條款
              </a>{' '}
              ·{' '}
              <a className="legal-inline-link" href="/privacy" target="_blank" rel="noopener noreferrer">
                隱私權政策
              </a>
            </div>
          </div>

          <Footer compact />
        </div>
      </div>
    </div>
  )
}
