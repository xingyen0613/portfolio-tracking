import { useState } from 'react'
import axios from 'axios'
import { GoogleLogin } from '@react-oauth/google'
import { useAuth } from '../../auth/AuthContext'
import { useDemo } from '../../context/DemoContext'
import { Icon } from '../Icon'

interface Props {
  close: () => void
  title?: string
  sub?: string
}

/** 預覽模式中需要真實帳號才能繼續的動作（如訂閱），用這個彈窗就地登入。 */
export default function LoginPromptModal({ close, title = '登入以繼續', sub }: Props) {
  const { login } = useAuth()
  const { exitDemo } = useDemo()
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleLogin(credential: string) {
    setLoading(true)
    setError(null)
    try {
      await login(credential)
      exitDemo()
      close()
    } catch (e: unknown) {
      const detail = axios.isAxiosError(e)
        ? e.response?.data?.detail ?? `${e.message}（HTTP ${e.response?.status ?? 'n/a'}）`
        : e instanceof Error ? e.message : String(e)
      setError(`登入失敗：${detail}`)
      setLoading(false)
    }
  }

  return (
    <div
      className="modal-backdrop"
      onClick={e => {
        if (e.target === e.currentTarget) close()
      }}
    >
      <div className="modal" style={{ maxWidth: 380 }}>
        <div className="modal-head">
          <div>
            <div className="modal-title">{title}</div>
            {sub && <div className="modal-sub">{sub}</div>}
          </div>
          <button className="modal-close" onClick={close} aria-label="關閉">
            <Icon name="x" />
          </button>
        </div>
        <div
          className="modal-body"
          style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14 }}
        >
          {loading ? (
            <span style={{ color: 'var(--fg-3)', fontSize: 13 }}>驗證中⋯</span>
          ) : (
            <GoogleLogin
              onSuccess={res => {
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

          <div style={{ fontSize: 11, color: 'var(--fg-3)', lineHeight: 1.5, textAlign: 'center' }}>
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
      </div>
    </div>
  )
}
