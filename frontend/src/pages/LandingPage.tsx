import { useState } from 'react'
import axios from 'axios'
import { GoogleLogin } from '@react-oauth/google'
import { useAuth } from '../auth/AuthContext'
import { useDemo } from '../context/DemoContext'
import Footer from '../components/Footer'
import LoginPromptModal from '../components/modals/LoginPromptModal'
import '../styles/landing.css'

interface Shot {
  src: string
  w: number
  h: number
}

interface Feature {
  eyebrow: string
  title: string
  desc: string
  shot: Shot
}

/** 影片區塊與 hero 共用的 dashboard 全景截圖。 */
const HERO_SHOT: Shot = { src: '/landing/hero-dashboard.png', w: 1600, h: 980 }

const FEATURES: Feature[] = [
  {
    eyebrow: 'Performance Metrics',
    title: '過去表現，一眼看完',
    desc: '各類別的餘額、1W 到 ALL 各區間的報酬率、Sharpe 值與最大回落，全部算好放在同一排卡片上。',
    shot: { src: '/landing/metrics.png', w: 1256, h: 244 },
  },
  {
    eyebrow: 'Asset Trend',
    title: '你的資產和大盤，同一張圖',
    desc: '每天記錄下來的部位變成一條連續的資產曲線，可依類別拆開檢視，也能疊上 S&P 500、NASDAQ 100、費半、0050、BTC 等比較基準——看看自己有沒有打贏大盤。',
    shot: { src: '/landing/trend.png', w: 1256, h: 425 },
  },
  {
    eyebrow: 'Allocation & Holdings by Source',
    title: '從配置比例看到持倉明細',
    desc: '圓餅圖看各類別佔比，點下去展開該類別的持倉明細；再往下依來源列出每個平台的完整部位，現金與期貨／合約也一併呈現。',
    shot: { src: '/landing/allocation-holdings.png', w: 1256, h: 726 },
  },
]

interface Platform {
  name: string
  logo?: string
  abbr?: string
  bg?: string
  fg?: string
}

interface Category {
  label: string
  accent: string
  /** 只有需要額外交代支援範圍的類別才寫。 */
  note?: string
  platforms: Platform[]
}

const CATEGORIES: Category[] = [
  {
    label: '加密貨幣',
    accent: 'var(--c-crypto)',
    note: '支援各家交易所以及鏈上錢包',
    platforms: [
      { name: 'Binance', logo: '/logos/binance.png' },
      { name: 'OKX', logo: '/logos/okx.png' },
      { name: 'Bybit', logo: '/logos/bybit.png' },
      { name: 'Hyperliquid', logo: '/logos/hyperliquid.png' },
      { name: 'EVM 錢包', logo: '/logos/evm.png' },
    ],
  },
  {
    label: '美股',
    accent: 'var(--c-us)',
    platforms: [{ name: 'Interactive Brokers', logo: '/logos/ibkr.png' }],
  },
  {
    label: '台股',
    accent: 'var(--c-tw)',
    platforms: [
      { name: '元大證券', abbr: 'YT', bg: '#004b99', fg: '#fff' },
      { name: '永豐證券', logo: '/logos/sinopac.jpg' },
      { name: '富邦證券', logo: '/logos/fubon.png' },
    ],
  },
  {
    label: '其他資產',
    accent: 'var(--c-other)',
    note: '支援手動匯入、自訂資產類別',
    platforms: [
      { name: '不動產', abbr: '房', bg: '#3a3a44', fg: '#fff' },
      { name: '保單', abbr: '保', bg: '#3a3a44', fg: '#fff' },
      { name: '現金', abbr: '$', bg: '#3a3a44', fg: '#fff' },
      { name: 'CSV 匯入', abbr: '＋', bg: '#3a3a44', fg: '#fff' },
    ],
  },
]

const STEPS = [
  { title: 'Google 登入', desc: '不用填表單，也可以先進預覽模式看看實際畫面。' },
  { title: '新增來源', desc: '選好平台，貼上唯讀權限的金鑰或錢包地址。' },
  { title: '等首次同步', desc: '數秒完成抓取，Dashboard 立刻長出你的部位。' },
  { title: '之後不用再管', desc: '每天自動記錄一次，資產曲線自己往前長。' },
]

function PlatformMark({ p }: { p: Platform }) {
  if (p.logo) return <img src={p.logo} alt="" width={20} height={20} loading="lazy" />
  return (
    <span className="lp-plat-abbr" style={{ background: p.bg, color: p.fg }}>
      {p.abbr}
    </span>
  )
}

/** hover 只綁在這個容器上，滑到旁邊的說明文字不會觸發展開。 */
function Shots({ shot }: { shot: Shot }) {
  return (
    <div className="lp-shots">
      <img src={shot.src} alt="" width={shot.w} height={shot.h} loading="lazy" />
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
  const [loginOpen, setLoginOpen] = useState(false)

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
      <div className="lp-bg" aria-hidden="true">
        <svg viewBox="0 0 1440 900" preserveAspectRatio="none">
          <defs>
            <linearGradient id="lp-line" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#fff" stopOpacity="0" />
              <stop offset="45%" stopColor="#fff" stopOpacity="0.5" />
              <stop offset="100%" stopColor="#b9b2ff" stopOpacity="0" />
            </linearGradient>
          </defs>
          <g fill="none" stroke="url(#lp-line)">
            <path d="M-40 210 C 320 120, 620 300, 900 190 S 1340 40, 1500 130" />
            <path d="M-40 300 C 300 200, 640 380, 920 260 S 1350 110, 1500 205" />
            <path d="M-40 395 C 280 285, 660 460, 940 335 S 1360 185, 1500 285" />
            <path d="M-40 495 C 260 375, 680 545, 960 415 S 1370 265, 1500 370" />
            <path d="M-40 600 C 240 470, 700 635, 980 500 S 1380 350, 1500 460" />
          </g>
        </svg>
      </div>

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
          <button className="lp-nav-login" onClick={() => setLoginOpen(true)}>
            登入
          </button>
        </nav>
      </header>

      {/* Hero：文案靠左，dashboard 卡片在右側旋轉定格 */}
      <section className="lp-hero">
        <div className="lp-hero-text">
          <h1 className="lp-hero-title">
            ALL IN
            <span>one portfolio tracker</span>
          </h1>
          <p className="lp-hero-sub">連接交易所、錢包與券商，在專屬儀表板一次掌握完整資產。</p>
        </div>

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
          <h2>連接一次，之後每天自動記錄</h2>
          <p>
            交易所、鏈上錢包、美股與台股券商各自連接一次，系統每天自動記錄一次你的投資部位——
            不必再手動更新試算表，也不會忘記某天沒記。
          </p>
        </div>

        <div className="lp-deck">
          {CATEGORIES.map(c => (
            <article className="lp-deck-card" key={c.label} style={{ ['--dot' as string]: c.accent }}>
              <div className="lp-deck-label">{c.label}</div>
              {c.note && <p className="lp-deck-note">{c.note}</p>}
              <ul className="lp-deck-list">
                {c.platforms.map(p => (
                  <li key={p.name}>
                    <PlatformMark p={p} />
                    <span>{p.name}</span>
                  </li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      </section>

      {/* 三個功能區塊：hover 展開成完整尺寸 */}
      {FEATURES.map((f, i) => (
        <section className={`lp-section lp-feature${i % 2 ? ' lp-feature-rev' : ''}`} key={f.eyebrow}>
          {/* eyebrow 留在區塊頂層，hover 展開時不跟著文字一起淡出 */}
          <div className="lp-eyebrow lp-feature-eyebrow">{f.eyebrow}</div>
          <div className="lp-feature-body">
            <div className="lp-feature-text">
              <h2>{f.title}</h2>
              <p>{f.desc}</p>
            </div>
            <Shots shot={f.shot} />
          </div>
        </section>
      ))}

      {/* 操作說明 */}
      <section className="lp-section">
        <div className="lp-section-head">
          <div className="lp-eyebrow">How it works</div>
          <h2>三分鐘連上第一個來源</h2>
        </div>

        <ol className="lp-steps">
          {STEPS.map((s, i) => (
            <li key={s.title}>
              <span className="lp-step-num">{i + 1}</span>
              <div>
                <div className="lp-step-title">{s.title}</div>
                <p>{s.desc}</p>
              </div>
            </li>
          ))}
        </ol>

        <div className="lp-video-frame">
          <img src={HERO_SHOT.src} alt="" width={HERO_SHOT.w} height={HERO_SHOT.h} loading="lazy" />
          <div className="lp-video-overlay">
            <span className="lp-video-play" aria-hidden="true" />
            <span className="lp-video-label">說明影片準備中</span>
          </div>
        </div>

        <div className="lp-howto-foot">
          <a className="lp-btn-primary" href="/guide">
            查看完整使用說明 →
          </a>
          <p className="lp-howto-note">六個步驟 · 16 張實際操作截圖，免登入可看。</p>
        </div>
      </section>

      <section className="lp-section lp-section-cta lp-section-cta-last">
        <h2 className="lp-final-title">立即體驗無需手動記錄的資產追蹤工具</h2>
        <Cta {...ctaProps} id="cta-bottom" />
      </section>

      <Footer sameTab />

      {loginOpen && <LoginPromptModal close={() => setLoginOpen(false)} title="登入 ALL IN" />}
    </div>
  )
}
