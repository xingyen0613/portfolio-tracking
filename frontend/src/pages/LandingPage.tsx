import { useState } from 'react'
import axios from 'axios'
import { GoogleLogin } from '@react-oauth/google'
import { useAuth } from '../auth/AuthContext'
import { useDemo } from '../context/DemoContext'
import Footer from '../components/Footer'
import { SOURCE_TEMPLATES } from '../data/sourceTemplates'
import '../styles/landing.css'

/** 產品截圖區塊：文字 + 3D 傾斜的 dashboard 畫面。 */
interface Shot {
  src: string
  w: number
  h: number
}

interface Feature {
  eyebrow: string
  title: string
  desc: string
  shots: Shot[]
}

/** 影片區塊與 hero 共用的 dashboard 全景截圖。 */
const HERO_SHOT: Shot = { src: '/landing/hero-dashboard.png', w: 1600, h: 980 }

const FEATURES: Feature[] = [
  {
    eyebrow: 'Performance Metrics',
    title: '過去表現，一眼看完',
    desc: '各類別的餘額、1W 到 ALL 各區間的報酬率、Sharpe 值與最大回落，全部算好放在同一排卡片上。',
    shots: [{ src: '/landing/metrics.png', w: 1256, h: 244 }],
  },
  {
    eyebrow: 'Asset Trend',
    title: '你的資產和大盤，同一張圖',
    desc: '歷史資產走勢可依類別拆開檢視，還能疊上 S&P 500、NASDAQ 100、費半、0050、BTC 等比較基準——看看自己有沒有打贏大盤。',
    shots: [{ src: '/landing/trend.png', w: 1256, h: 425 }],
  },
  {
    eyebrow: 'Allocation & Holdings by Source',
    title: '從配置比例，下鑽到每一筆持倉',
    desc: '圓餅圖看各類別佔比，點下去展開該類別的持倉明細；再往下依來源列出每個平台的完整部位，現金與期貨／合約也一併呈現。',
    shots: [
      { src: '/landing/allocation.png', w: 1256, h: 235 },
      { src: '/landing/holdings.png', w: 1256, h: 464 },
    ],
  },
]

const SOURCE_GROUPS = [
  {
    label: '加密貨幣',
    accent: 'var(--c-crypto)',
    desc: '交易所 API 與鏈上錢包地址，現貨、合約與未實現損益分開計算。',
    items: ['Binance', 'OKX', 'Bybit', 'MEXC', '派網 Pionex', 'Hyperliquid', 'EVM / Solana / SUI 錢包'],
  },
  {
    label: '美股',
    accent: 'var(--c-us)',
    desc: '券商官方介面直接抓取持倉與現金餘額，不必手動維護。',
    items: ['Interactive Brokers'],
  },
  {
    label: '台股',
    accent: 'var(--c-tw)',
    desc: '串接券商 API 或對帳單，現股、零股、擔保品與期權權益一起看。',
    items: ['元大證券', '永豐證券', '富邦證券'],
  },
  {
    label: '其他資產',
    accent: 'var(--c-other)',
    desc: '沒有 API 的資產也不漏掉，用 CSV 匯入即可納入總資產與歷史走勢。',
    items: ['不動產', '保單', '現金', '自訂資產'],
  },
]

const LOGO_WALL = SOURCE_TEMPLATES.filter(t => t.implemented && t.id !== 'manual')

function Shots({ shots }: { shots: Shot[] }) {
  return (
    <div className={`lp-shots${shots.length > 1 ? ' lp-shots-stack' : ''}`}>
      {shots.map(s => (
        <div className="lp-shot" key={s.src}>
          <img src={s.src} alt="" width={s.w} height={s.h} loading="lazy" />
        </div>
      ))}
    </div>
  )
}

function Cta({
  onLogin,
  onDemo,
  loading,
  error,
  id,
}: {
  onLogin: (credential: string) => void
  onDemo: () => void
  loading: boolean
  error: string | null
  id: string
}) {
  return (
    <div className="lp-cta">
      {loading ? (
        <span className="lp-cta-loading">驗證中⋯</span>
      ) : (
        <div className="lp-cta-google">
          <GoogleLogin
            key={id}
            onSuccess={res => {
              if (res.credential) onLogin(res.credential)
            }}
            onError={() => onLogin('')}
            theme="filled_black"
            shape="pill"
            text="signin_with"
            size="large"
            width="260"
          />
        </div>
      )}

      <button className="lp-btn-ghost" onClick={onDemo}>
        預覽模式（免登入）
      </button>

      {error && <div className="lp-error">{error}</div>}

      <p className="lp-cta-legal">
        繼續即代表您同意我們的{' '}
        <a href="/terms" target="_blank" rel="noopener noreferrer">
          服務條款
        </a>{' '}
        ·{' '}
        <a href="/privacy" target="_blank" rel="noopener noreferrer">
          隱私權政策
        </a>
      </p>
    </div>
  )
}

export default function LandingPage() {
  const { login } = useAuth()
  const { enterDemo } = useDemo()
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleLogin(credential: string) {
    if (!credential) {
      setError('Google 登入失敗，請再試一次')
      return
    }
    setLoading(true)
    setError(null)
    try {
      await login(credential)
    } catch (e: unknown) {
      const detail = axios.isAxiosError(e)
        ? e.response?.data?.detail ?? `${e.message}（HTTP ${e.response?.status ?? 'n/a'}）`
        : e instanceof Error
          ? e.message
          : String(e)
      setError(`登入失敗：${detail}`)
    } finally {
      setLoading(false)
    }
  }

  const ctaProps = { onLogin: handleLogin, onDemo: enterDemo, loading, error }

  return (
    <div className="lp">
      <div className="lp-bg" aria-hidden="true" />

      <header className="lp-nav">
        <a className="lp-brand" href="/">
          <span className="lp-brand-mark" />
          <span>
            <span className="lp-brand-name">ALL IN</span>
            <span className="lp-brand-sub">Portfolio tracker</span>
          </span>
        </a>
        <nav className="lp-nav-links">
          <a href="/guide">使用說明</a>
          <a href="/preview/dashboard">預覽模式</a>
        </nav>
      </header>

      {/* Hero */}
      <section className="lp-hero">
        <h1 className="lp-hero-title">
          ALL IN
          <span>one portfolio tracker</span>
        </h1>
        <p className="lp-hero-sub">
          連接交易所、錢包與券商，在專屬儀表板一次掌握完整資產。
        </p>

        <div className="lp-hero-shot">
          <img src={HERO_SHOT.src} alt="ALL IN Dashboard" width={HERO_SHOT.w} height={HERO_SHOT.h} />
        </div>
      </section>

      <section className="lp-section lp-section-cta">
        <Cta {...ctaProps} id="cta-top" />
      </section>

      {/* 資料來源 */}
      <section className="lp-section">
        <div className="lp-section-head">
          <div className="lp-eyebrow">Sources</div>
          <h2>散在各處的資產，收進同一個帳本</h2>
          <p>
            加密貨幣交易所、鏈上錢包、美股與台股券商各自連接一次，之後每天自動同步。
            沒有 API 的資產也能用 CSV 補上。
          </p>
        </div>

        <div className="lp-source-grid">
          {SOURCE_GROUPS.map(g => (
            <div className="lp-source-card" key={g.label}>
              <div className="lp-source-label" style={{ ['--dot' as string]: g.accent }}>
                {g.label}
              </div>
              <p>{g.desc}</p>
              <ul>
                {g.items.map(i => (
                  <li key={i}>{i}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="lp-logo-wall">
          {LOGO_WALL.map(t => (
            <div className="lp-logo" key={t.id} title={t.name}>
              {t.logoUrl ? (
                <img src={t.logoUrl} alt={t.name} loading="lazy" />
              ) : (
                <span className="lp-logo-abbr" style={{ background: t.color, color: t.textColor }}>
                  {t.abbr}
                </span>
              )}
              <span className="lp-logo-name">{t.name}</span>
            </div>
          ))}
        </div>
      </section>

      {/* 三個功能區塊 */}
      {FEATURES.map((f, i) => (
        <section className={`lp-section lp-feature${i % 2 ? ' lp-feature-rev' : ''}`} key={f.eyebrow}>
          <div className="lp-feature-text">
            <div className="lp-eyebrow">{f.eyebrow}</div>
            <h2>{f.title}</h2>
            <p>{f.desc}</p>
          </div>
          <Shots shots={f.shots} />
        </section>
      ))}

      {/* 操作說明 */}
      <section className="lp-section">
        <div className="lp-section-head">
          <div className="lp-eyebrow">How it works</div>
          <h2>三分鐘連上第一個來源</h2>
          <p>看影片跟著操作，或直接翻圖文說明——從申請 API 金鑰到看懂每張圖表都寫在裡面。</p>
        </div>

        <div className="lp-howto">
          <div className="lp-video">
            <div className="lp-video-frame">
              <img src={HERO_SHOT.src} alt="" width={HERO_SHOT.w} height={HERO_SHOT.h} loading="lazy" />
              <div className="lp-video-overlay">
                <span className="lp-video-play" aria-hidden="true" />
                <span className="lp-video-label">說明影片準備中</span>
              </div>
            </div>
          </div>

          <div className="lp-howto-side">
            <div className="lp-howto-steps">
              <div>
                <span>1</span>Google 登入，或先進預覽模式看看
              </div>
              <div>
                <span>2</span>新增來源，貼上唯讀 API 金鑰或錢包地址
              </div>
              <div>
                <span>3</span>等數秒完成首次同步，之後每天自動更新
              </div>
            </div>
            <a className="lp-btn-primary" href="/guide">
              查看完整使用說明 →
            </a>
            <p className="lp-howto-note">六個步驟 · 16 張實際操作截圖，免登入可看。</p>
          </div>
        </div>
      </section>

      <section className="lp-section lp-section-cta lp-section-cta-last">
        <h2 className="lp-final-title">把所有部位，放進同一個畫面</h2>
        <Cta {...ctaProps} id="cta-bottom" />
      </section>

      <Footer sameTab />
    </div>
  )
}
