import { useEffect, useState } from 'react'
import { Icon } from './Icon'
import { SUPPORT_EMAIL, SUPPORT_TELEGRAM, SUPPORT_TELEGRAM_URL } from '../legal/contact'

interface Fig {
  src: string
  caption: string
}

type Block =
  | { kind: 'p'; text: string }
  | { kind: 'note'; tone: 'warn' | 'info'; title: string; text: string }
  | { kind: 'figs'; items: Fig[] }
  | { kind: 'feature'; term: string; desc: string; items: Fig[] }

interface Step {
  title: string
  blocks: Block[]
}

const IMG = (n: number) => `/guide/step-${String(n).padStart(2, '0')}.jpg`

const STEPS: Step[] = [
  {
    title: '新增第一個資料來源',
    blocks: [
      {
        kind: 'p',
        text: '登入後會進入 Dashboard。有三個地方都可以開始新增部位來源（紅框處）：左側選單的 Sources、右上角的「新增來源」，以及畫面中央的「新增資料來源」。',
      },
      {
        kind: 'figs',
        items: [
          { src: IMG(1), caption: '圖 1 — Dashboard 上的三個新增入口' },
          { src: IMG(2), caption: '圖 2 — Sources 頁同樣可以新增來源' },
        ],
      },
    ],
  },
  {
    title: '選擇來源類型',
    blocks: [
      {
        kind: 'p',
        text: '「新增資料來源」視窗出現後，選擇你要連接的平台。上方可依加密貨幣、美股、台股等分類篩選；標示「即將推出」的來源代表尚未開放。',
      },
      { kind: 'figs', items: [{ src: IMG(3), caption: '圖 3 — 支援的來源清單' }] },
    ],
  },
  {
    title: '填入憑證並連接',
    blocks: [
      {
        kind: 'p',
        text: '以 Binance 為例：點選後需要填入該平台的 API 金鑰，系統才能查詢你的持有部位。不知道去哪申請，可以點左下角「取得 API」直接跳轉到該來源的申請頁面。「來源名稱」可自行命名，方便區分同一平台底下的多個帳戶。',
      },
      {
        kind: 'p',
        text: '確認輸入完成後點擊右下角「連接並同步」，等待數秒即完成首次部位抓取，看到「已連接」就代表成功。',
      },
      {
        kind: 'figs',
        items: [
          { src: IMG(4), caption: '圖 4 — 填寫憑證與來源名稱' },
          { src: IMG(5), caption: '圖 5 — 連接成功' },
        ],
      },
      {
        kind: 'note',
        tone: 'warn',
        title: '只授權唯讀權限',
        text: '不論任何來源，請確保提供的金鑰權限僅為「唯讀（Read）」，切勿開啟交易、提款或任何寫入權限。另外，不同來源需要的資訊（API 金鑰、憑證、錢包地址）不盡相同，連接前請先確認選對平台。',
      },
    ],
  },
  {
    title: '回到 Dashboard 查看你的部位',
    blocks: [
      {
        kind: 'p',
        text: '完成後從左側選單回到 Dashboard，就能看到整體資產狀況，由上而下分為四個區塊。',
      },
      {
        kind: 'feature',
        term: 'Performance Metrics',
        desc: '查看各類別的餘額、各時間區間的報酬率、Sharpe 值與最大回落，讓你清楚自己過去的表現。',
        items: [{ src: IMG(6), caption: '圖 6 — 可切換 1W 至 ALL 的統計區間' }],
      },
      {
        kind: 'feature',
        term: 'Asset Trend',
        desc: '將資產變動視覺化呈現。除了依類別分別檢視，還能與 S&P 500、NASDAQ 100、費半、0050、BTC 等指數比較，看看自己有沒有擊敗大盤。',
        items: [
          { src: IMG(7), caption: '圖 7 — 依類別檢視歷史資產走勢' },
          { src: IMG(8), caption: '圖 8 — 切換報酬率 % 並疊上比較基準' },
        ],
      },
      {
        kind: 'feature',
        term: 'Allocation',
        desc: '以圓餅圖檢視各類別資產的比例，點擊任一類別可展開該類別內的持倉佔比。',
        items: [
          { src: IMG(9), caption: '圖 9 — 資產類別佔比' },
          { src: IMG(10), caption: '圖 10 — 點擊後展開該類別持倉' },
        ],
      },
      {
        kind: 'feature',
        term: 'Holdings by Source',
        desc: '依各來源整理最詳細的持倉明細，不只有股票與幣種，現金與期貨／合約部位也一併列出。',
        items: [
          { src: IMG(11), caption: '圖 11 — 點擊任一來源可展開明細' },
          { src: IMG(12), caption: '圖 12 — 現股、現金與期貨分段呈現' },
        ],
      },
    ],
  },
  {
    title: '日常操作',
    blocks: [
      {
        kind: 'feature',
        term: '頂端工具列',
        desc: '右上角可切換 USD／TWD 顯示幣別，方便換算。當持倉數據沒有即時更新時，點擊刷新圖示即可手動觸發一次查詢。',
        items: [{ src: IMG(13), caption: '圖 13 — 幣別切換與手動刷新' }],
      },
      {
        kind: 'feature',
        term: 'Sources 頁',
        desc: '每個來源右側的功能由左至右依序為：目前同步狀態、匯入歷史資料（請依視窗中的格式提供 CSV）、編輯來源資訊、手動刷新、移除來源。',
        items: [
          { src: IMG(14), caption: '圖 14 — 來源列右側的五項功能' },
          { src: IMG(15), caption: '圖 15 — 匯入歷史資料的 CSV 格式說明' },
        ],
      },
      {
        kind: 'feature',
        term: 'Settings 頁',
        desc: '在此加入訂閱，取得更完整的工具體驗。',
        items: [{ src: IMG(16), caption: '圖 16 — 訂閱區塊就在本頁上方' }],
      },
    ],
  },
]

/** 說明步驟數（含最後的「回報問題與建議」）。 */
export const GUIDE_STEP_COUNT = STEPS.length + 1

function Figure({ fig, onOpen }: { fig: Fig; onOpen: (src: string) => void }) {
  return (
    <figure className="guide-fig">
      <img src={fig.src} alt={fig.caption} loading="lazy" onClick={() => onOpen(fig.src)} />
      <figcaption>{fig.caption}</figcaption>
    </figure>
  )
}

function Figs({ items, onOpen }: { items: Fig[]; onOpen: (src: string) => void }) {
  return (
    <div className="guide-figs">
      {items.map(f => (
        <Figure key={f.src} fig={f} onOpen={onOpen} />
      ))}
    </div>
  )
}

function Lightbox({ src, close }: { src: string; close: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && close()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [close])

  return (
    <div className="modal-backdrop guide-lightbox" onClick={close}>
      <img src={src} alt="" />
      <button className="modal-close guide-lightbox-close" onClick={close} aria-label="關閉">
        <Icon name="x" />
      </button>
    </div>
  )
}

/**
 * 圖文說明的正文，Settings 的 modal 與公開頁 /guide 共用。
 * 點圖放大的 lightbox 由本元件自行管理。
 */
export default function GuideContent() {
  const [zoom, setZoom] = useState<string | null>(null)

  return (
    <>
      {STEPS.map((step, i) => (
        <section className="guide-step" key={step.title}>
          <div className="guide-step-head">
            <span className="guide-step-num">{i + 1}</span>
            <h4>{step.title}</h4>
          </div>
          <div className="guide-step-body">
            {step.blocks.map((b, j) => {
              if (b.kind === 'p') return <p key={j}>{b.text}</p>
              if (b.kind === 'figs') return <Figs key={j} items={b.items} onOpen={setZoom} />
              if (b.kind === 'note')
                return (
                  <div key={j} className={`guide-note guide-note-${b.tone}`}>
                    <Icon name="info" className="guide-note-icon" />
                    <div>
                      <strong>{b.title}</strong>
                      <span>{b.text}</span>
                    </div>
                  </div>
                )
              return (
                <div key={j} className="guide-feature">
                  <p>
                    <strong>{b.term}</strong>
                    {b.desc}
                  </p>
                  <Figs items={b.items} onOpen={setZoom} />
                </div>
              )
            })}
          </div>
        </section>
      ))}

      <section className="guide-step">
        <div className="guide-step-head">
          <span className="guide-step-num">{STEPS.length + 1}</span>
          <h4>回報問題與建議</h4>
        </div>
        <div className="guide-step-body">
          <p>
            使用上遇到任何問題，或想提供功能與更新建議，都歡迎透過頁面下方的聯絡管道告訴我們：
            <a href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a>
            {' · '}
            <a href={SUPPORT_TELEGRAM_URL} target="_blank" rel="noopener noreferrer">
              @{SUPPORT_TELEGRAM}
            </a>
          </p>
        </div>
      </section>

      {zoom && <Lightbox src={zoom} close={() => setZoom(null)} />}
    </>
  )
}
