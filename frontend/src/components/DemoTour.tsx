import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useDemo } from '../context/DemoContext'
import type { Route } from '../App'

interface TourStep {
  title: string
  body: string
  targets: string[]
  /** 該步驟的目標元素所在分頁，切換步驟時一併切過去 */
  route: Route
}

const STEPS: TourStep[] = [
  {
    title: '新增來源',
    body: '從左側 Sources 或右上角的按鈕，加入交易所、錢包或券商作為資料來源。',
    targets: ['[data-tour="sidebar-sources"]', '[data-tour="add-source-btn"]'],
    route: 'dashboard',
  },
  {
    title: 'Performance Metrics',
    body: '一眼掌握各類資產的當前表現與漲跌幅。',
    targets: ['[data-tour="perf-metrics"]'],
    route: 'dashboard',
  },
  {
    title: 'Asset Trend',
    body: '查看歷史資產淨值走勢，並可與其他 benchmark 比較。',
    targets: ['[data-tour="asset-trend"]'],
    route: 'dashboard',
  },
  {
    title: 'Allocation & Holdings by Source',
    body: '深入每個來源的資產配置與詳細持倉細節。',
    targets: ['[data-tour="allocation"]', '[data-tour="holdings"]'],
    route: 'dashboard',
  },
  {
    title: '訂閱方案',
    body: 'Settings 頁的 Subscription 區塊可開通訂閱，啟用每日自動同步、細部持倉明細與 benchmark 回測比較。',
    targets: ['[data-tour="subscription"]'],
    route: 'settings',
  },
  {
    title: '使用說明',
    body: '不確定怎麼開始？同一頁下方的「使用說明」有完整圖文教學，從連接第一個來源到看懂各項圖表。',
    targets: ['[data-tour="guide"]'],
    route: 'settings',
  },
]

const PAD = 8
const RADIUS = 10
const TIP_W = 320
const GAP = 16

interface Hole {
  x: number
  y: number
  w: number
  h: number
}

export default function DemoTour({ setRoute }: { setRoute: (r: Route) => void }) {
  const { tourActive, endTour } = useDemo()
  const [step, setStep] = useState(0)
  const [holes, setHoles] = useState<Hole[]>([])
  const [tipH, setTipH] = useState(180)
  const tipRef = useRef<HTMLDivElement>(null)

  const measure = useCallback(() => {
    const cur = STEPS[step]
    const rects: Hole[] = []
    for (const sel of cur.targets) {
      const el = document.querySelector(sel)
      if (!el) continue
      const r = el.getBoundingClientRect()
      rects.push({
        x: r.left - PAD,
        y: r.top - PAD,
        w: r.width + PAD * 2,
        h: r.height + PAD * 2,
      })
    }
    setHoles(rects)
  }, [step])

  // Reset to step 0 whenever a fresh tour starts
  useEffect(() => {
    if (tourActive) setStep(0)
  }, [tourActive])

  // On step change: scroll first target into view, then measure
  useEffect(() => {
    if (!tourActive) return
    const first = document.querySelector(STEPS[step].targets[0])
    first?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    measure()
    // 切換分頁的步驟：等新頁面渲染與捲動歸零後再量一次
    const t1 = setTimeout(measure, 120)
    const t2 = setTimeout(measure, 400)
    return () => {
      clearTimeout(t1)
      clearTimeout(t2)
    }
  }, [tourActive, step, measure])

  // Recompute holes on resize / scroll (capture inner scroll containers)
  useEffect(() => {
    if (!tourActive) return
    const onChange = () => measure()
    window.addEventListener('resize', onChange)
    window.addEventListener('scroll', onChange, true)
    return () => {
      window.removeEventListener('resize', onChange)
      window.removeEventListener('scroll', onChange, true)
    }
  }, [tourActive, measure])

  // Measure tooltip height for accurate placement
  useLayoutEffect(() => {
    if (tipRef.current) setTipH(tipRef.current.offsetHeight)
  }, [step, holes])

  if (!tourActive) return null

  const isLast = step === STEPS.length - 1
  const goto = (i: number) => {
    setRoute(STEPS[i].route)
    setStep(i)
  }
  const next = () => (isLast ? endTour() : goto(step + 1))
  const prev = () => goto(Math.max(0, step - 1))

  // Union of holes → anchor for tooltip placement
  const vw = window.innerWidth
  const vh = window.innerHeight
  let tipTop: number
  let tipLeft: number
  if (holes.length) {
    const left = Math.min(...holes.map(h => h.x))
    const right = Math.max(...holes.map(h => h.x + h.w))
    const top = Math.min(...holes.map(h => h.y))
    const bottom = Math.max(...holes.map(h => h.y + h.h))
    const belowTop = bottom + GAP
    tipTop = belowTop + tipH > vh - GAP ? top - tipH - GAP : belowTop
    tipTop = Math.min(Math.max(tipTop, GAP), vh - tipH - GAP)
    tipLeft = (left + right) / 2 - TIP_W / 2
    tipLeft = Math.min(Math.max(tipLeft, GAP), vw - TIP_W - GAP)
  } else {
    tipTop = vh / 2 - tipH / 2
    tipLeft = vw / 2 - TIP_W / 2
  }

  const cur = STEPS[step]

  return (
    <>
      {/* Click blocker — tour is button-driven, background is inert */}
      <div
        style={{ position: 'fixed', inset: 0, zIndex: 300 }}
        onClick={e => e.stopPropagation()}
      />

      {/* Dimming mask with spotlight cut-outs */}
      <svg
        width="100%"
        height="100%"
        style={{ position: 'fixed', inset: 0, zIndex: 301, pointerEvents: 'none' }}
      >
        <defs>
          <mask id="demo-tour-mask">
            <rect x={0} y={0} width="100%" height="100%" fill="white" />
            {holes.map((h, i) => (
              <rect key={i} x={h.x} y={h.y} width={h.w} height={h.h} rx={RADIUS} fill="black" />
            ))}
          </mask>
        </defs>
        <rect
          x={0}
          y={0}
          width="100%"
          height="100%"
          fill="rgba(6,6,10,0.72)"
          mask="url(#demo-tour-mask)"
          style={{ transition: 'fill 150ms ease-out' }}
        />
        {holes.map((h, i) => (
          <rect
            key={i}
            x={h.x}
            y={h.y}
            width={h.w}
            height={h.h}
            rx={RADIUS}
            fill="none"
            stroke="var(--accent)"
            strokeWidth={1.5}
            opacity={0.9}
          />
        ))}
      </svg>

      {/* Tooltip / instruction dialog */}
      <div
        ref={tipRef}
        style={{
          position: 'fixed',
          top: tipTop,
          left: tipLeft,
          width: TIP_W,
          zIndex: 302,
          background: 'var(--bg-elev)',
          border: '1px solid var(--bdr)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: 'var(--shadow-pop)',
          padding: '18px 20px',
          animation: 'fadeIn 150ms ease-out',
        }}
      >
        <div style={{ fontSize: 11, color: 'var(--accent)', fontWeight: 600, marginBottom: 6, letterSpacing: '0.02em' }}>
          步驟 {step + 1} / {STEPS.length}
        </div>
        <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--fg)', marginBottom: 6 }}>
          {cur.title}
        </div>
        <div style={{ fontSize: 13, color: 'var(--fg-2)', lineHeight: 1.6, marginBottom: 16 }}>
          {cur.body}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button
            onClick={endTour}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: 'var(--fg-3)', fontSize: 12, padding: '4px 2px',
            }}
          >
            跳過
          </button>
          <div style={{ flex: 1 }} />
          {step > 0 && (
            <button className="btn" onClick={prev}>
              上一步
            </button>
          )}
          <button className="btn btn-primary" onClick={next}>
            {isLast ? '完成' : '下一步'}
          </button>
        </div>
      </div>
    </>
  )
}
