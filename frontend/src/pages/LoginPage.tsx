import { useState } from 'react'
import { GoogleLogin } from '@react-oauth/google'
import { useAuth } from '../auth/AuthContext'

export default function LoginPage() {
  const { login } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleLogin(credential: string) {
    setLoading(true)
    setError(null)
    try {
      await login(credential)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      setError(`登入失敗：${msg}`)
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
              Every account.
              <br />
              One number.
            </div>
            <div className="m-sub" style={{ marginBottom: 32 }}>
              Connect exchanges, wallets and brokers — track your full portfolio in one
              private dashboard.
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

            <div
              className="m-foot"
              style={{
                marginTop: 18,
                fontSize: 11,
                color: 'var(--fg-3)',
                lineHeight: 1.5,
              }}
            >
              By continuing you agree to our
              <br />
              <span style={{ color: 'var(--fg-2)' }}>Terms</span> ·{' '}
              <span style={{ color: 'var(--fg-2)' }}>Privacy</span>
            </div>
          </div>

          <div className="m-foot">© 2026 ALL IN</div>
        </div>
      </div>
    </div>
  )
}
