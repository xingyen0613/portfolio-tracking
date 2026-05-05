import { GoogleLogin } from '@react-oauth/google'
import { useAuth } from '../auth/AuthContext'

export default function LoginPage() {
  const { login } = useAuth()

  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      height: '100vh', background: 'var(--bg)', fontFamily: "'Plus Jakarta Sans', sans-serif",
    }}>
      <div style={{
        background: 'var(--surf)', border: '1px solid var(--bdr)', borderRadius: 12,
        padding: '40px 48px', display: 'flex', flexDirection: 'column',
        alignItems: 'center', gap: 28, minWidth: 320,
      }}>
        {/* Brand */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--blue)' }} />
          <span style={{ fontSize: 20, fontWeight: 700, color: 'var(--fg1)' }}>Portfolio</span>
        </div>

        <div style={{ textAlign: 'center', color: 'var(--fg2)', fontSize: 13, lineHeight: 1.6 }}>
          <div style={{ fontWeight: 600, color: 'var(--fg1)', marginBottom: 4 }}>個人資產追蹤</div>
          使用 Google 帳號登入以存取您的資產 Dashboard
        </div>

        <GoogleLogin
          onSuccess={res => {
            if (res.credential) login(res.credential)
          }}
          onError={() => console.error('Google login failed')}
          useOneTap
          theme="filled_black"
          shape="pill"
          text="signin_with"
        />
      </div>
    </div>
  )
}
