import { useEffect, useRef, useState } from 'react'
import {
  createChart, ColorType, LineSeries, LineStyle,
  type IChartApi, type ISeriesApi,
} from 'lightweight-charts'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'
import { useCurrency } from '../../context/CurrencyContext'
import { useDemo } from '../../context/DemoContext'
import { DEMO_HISTORY, DEMO_BENCHMARKS, DEMO_SNAPSHOT } from '../../data/demoData'

// ── Portfolio constants ──────────────────────────────────────────────────────

const P_COLORS = { total: '#7c6ef5', crypto: '#f0a23c', us_stock: '#ec5b7e', tw_stock: '#4ec9a8' } as const
const P_LABELS = { total: '總資產', crypto: '幣圈', us_stock: '美股', tw_stock: '台股' } as const
type PKey = keyof typeof P_COLORS
const P_KEYS: PKey[] = ['total', 'crypto', 'us_stock', 'tw_stock']

// ── Benchmark constants ──────────────────────────────────────────────────────

const B_TICKERS = ['^GSPC', '0050.TW', 'BTC-USD'] as const
type BTicker = typeof B_TICKERS[number]

const B_COLORS: Record<BTicker, string> = {
  '^GSPC':   '#a371f7',
  '0050.TW': '#39d353',
  'BTC-USD': '#f0883e',
}
const B_LABELS: Record<BTicker, string> = {
  '^GSPC':   'S&P 500',
  '0050.TW': '0050',
  'BTC-USD': 'BTC',
}

// ── Time windows ─────────────────────────────────────────────────────────────

// ── Types ─────────────────────────────────────────────────────────────────────

interface HistoryData {
  dates: string[]
  series: Record<PKey, number[]>
  latest: Record<PKey, number>
  metrics: Record<PKey, { total_return: number | null; sharpe: number | null; mdd: number | null }>
}

interface BenchmarkSeries { ticker: string; label: string; color: string; dates: string[]; closes: number[] }
interface BenchmarkData { benchmarks: BenchmarkSeries[] }

interface SnapshotItem     { symbol: string; pct: number }
interface SnapshotCategory { actual_date: string | null; items: SnapshotItem[] }
interface SnapshotData     { date: string; categories: Record<string, SnapshotCategory> }

const CAT_KEYS: PKey[] = ['us_stock', 'crypto', 'tw_stock']

// ── Formatters ────────────────────────────────────────────────────────────────


// converts Lightweight Charts Time (string | number | BusinessDay) → 'YYYY-MM-DD'
function lwcTimeToStr(t: unknown): string {
  if (typeof t === 'string') return t
  if (typeof t === 'number') return new Date(t * 1000).toISOString().slice(0, 10)
  const bd = t as { year: number; month: number; day: number }
  return `${bd.year}-${String(bd.month).padStart(2, '0')}-${String(bd.day).padStart(2, '0')}`
}

const PCT_FORMAT = {
  type: 'custom' as const,
  formatter: (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`,
  minMove: 0.01,
}
const USD_FORMAT = { type: 'price' as const, precision: 0, minMove: 1 }

// ── Tooltip renderer ──────────────────────────────────────────────────────────

function renderTooltip({
  tooltip, portData, containerRef, snap, snapshotFetching, fmt,
}: {
  tooltip:          { x: number; y: number; idx: number }
  portData:         HistoryData
  containerRef:     React.RefObject<HTMLDivElement | null>
  snap:             SnapshotData | null
  snapshotFetching: boolean
  fmt:              (usd: number) => string
}) {
  const containerW = containerRef.current?.clientWidth ?? 600
  const flipLeft   = tooltip.x > containerW * 0.65
  const hovDate    = portData.dates[tooltip.idx]

  return (
    <div style={{
      position: 'absolute',
      left: flipLeft ? Math.max(0, tooltip.x - 224) : tooltip.x + 14,
      top:  Math.max(4, tooltip.y - 10),
      background: '#111114',
      border: '1px solid #26262e',
      borderRadius: 7,
      padding: '9px 12px',
      fontSize: 11,
      fontFamily: 'JetBrains Mono, monospace',
      pointerEvents: 'none',
      zIndex: 10,
      width: 210,
    }}>
      <div style={{ color: 'var(--fg3)', fontSize: 10, marginBottom: 7 }}>{hovDate}</div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 8 }}>
        <div style={{ width: 6, height: 6, borderRadius: '50%', background: P_COLORS.total, flexShrink: 0 }} />
        <span style={{ color: 'var(--fg2)', flex: 1 }}>總資產</span>
        <span style={{ color: 'var(--fg1)' }}>{fmt(portData.series.total?.[tooltip.idx] ?? 0)}</span>
      </div>

      <div style={{ borderTop: '1px solid #30363d', marginBottom: 8 }} />

      {snapshotFetching && !snap && (
        <div style={{ color: 'var(--fg3)', fontSize: 10, marginBottom: 6 }}>載入明細...</div>
      )}

      {CAT_KEYS.map(key => {
        const catVal = portData.series[key]?.[tooltip.idx]
        if (!catVal) return null
        const catSnap  = snap?.categories[key]
        const topItems = catSnap?.items.slice(0, 4) ?? []
        const rest     = (catSnap?.items.length ?? 0) - topItems.length
        const isStale  = catSnap?.actual_date && catSnap.actual_date !== hovDate

        return (
          <div key={key} style={{ marginBottom: 7 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 3 }}>
              <div style={{ width: 6, height: 6, borderRadius: '50%', background: P_COLORS[key], flexShrink: 0 }} />
              <span style={{ color: 'var(--fg2)', flex: 1 }}>{P_LABELS[key]}</span>
              <span style={{ color: 'var(--fg1)' }}>{fmt(catVal)}</span>
            </div>
            {snap && topItems.length === 0 && (
              <div style={{ paddingLeft: 13, color: 'var(--fg3)', fontSize: 10 }}>無明細資料</div>
            )}
            {topItems.map(item => (
              <div key={item.symbol} style={{ display: 'flex', gap: 6, paddingLeft: 13, marginBottom: 1 }}>
                <span style={{ color: 'var(--fg3)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis' }}>{item.symbol}</span>
                <span style={{ color: 'var(--fg2)' }}>{item.pct.toFixed(1)}%</span>
              </div>
            ))}
            {rest > 0 && (
              <div style={{ paddingLeft: 13, color: 'var(--fg3)', fontSize: 10 }}>+{rest} 更多</div>
            )}
            {isStale && (
              <div style={{ paddingLeft: 13, color: 'var(--fg3)', fontSize: 9, marginTop: 1 }}>
                資料：{catSnap!.actual_date}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function TrendTab() {
  const { isDemo } = useDemo()
  const [mode, setMode] = useState<'USD' | 'return'>('USD')
  const { currency, convert, fmt } = useCurrency()
  const [pVis, setPVis] = useState<Record<PKey, boolean>>(
    () => Object.fromEntries(P_KEYS.map(k => [k, true])) as Record<PKey, boolean>
  )
  const [bVis, setBVis] = useState<Record<BTicker, boolean>>(
    () => Object.fromEntries(B_TICKERS.map(t => [t, true])) as Record<BTicker, boolean>
  )

  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef     = useRef<IChartApi | null>(null)
  const pSeriesMap   = useRef<Partial<Record<PKey, ISeriesApi<'Line'>>>>({})
  const bSeriesMap   = useRef<Partial<Record<BTicker, ISeriesApi<'Line'>>>>({})

  // raw data refs for dynamic % baseline recalculation
  const rawPortRef  = useRef<Partial<Record<PKey, number[]>>>({})
  const rawBenchRef = useRef<Partial<Record<BTicker, { dates: string[]; closes: number[] }>>>({})
  const isRecalc    = useRef(false)

  const [tooltip, setTooltip]           = useState<{ x: number; y: number; idx: number } | null>(null)
  const [snapshotDate, setSnapshotDate] = useState<string | null>(null)
  const portDataRef = useRef<HistoryData | null>(null)

  // ── Data queries ─────────────────────────────────────────────────────────────
  // 圖表永遠顯示全部資料，win 只控制下方 stat cards 的收益計算區間

  const { data: portData, isLoading } = useQuery<HistoryData>({
    queryKey: ['portfolio/history/all'],
    queryFn: () => api.get('/api/portfolio/history?window=all').then(r => r.data),
    enabled: !isDemo,
    initialData: isDemo ? DEMO_HISTORY : undefined,
  })

  const { data: benchData } = useQuery<BenchmarkData>({
    queryKey: ['benchmarks/all'],
    queryFn: () =>
      api.get('/api/benchmarks?tickers=%5EGSPC,0050.TW,BTC-USD&start=2015-01-01').then(r => r.data),
    enabled: !isDemo,
    initialData: isDemo ? DEMO_BENCHMARKS : undefined,
  })

  // keep portDataRef current so the crosshair handler (closed at chart init) always sees latest data
  useEffect(() => { portDataRef.current = portData ?? null }, [portData])

  // debounce: fetch snapshot data 350ms after crosshair stops on a date
  const tooltipIdx = tooltip?.idx ?? -1
  useEffect(() => {
    if (tooltipIdx === -1) { setSnapshotDate(null); return }
    const date = portDataRef.current?.dates[tooltipIdx]
    if (!date) { setSnapshotDate(null); return }
    const t = setTimeout(() => setSnapshotDate(date), 350)
    return () => clearTimeout(t)
  }, [tooltipIdx])

  const { data: snapshotData, isFetching: snapshotFetching } = useQuery<SnapshotData>({
    queryKey: ['portfolio/snapshot', snapshotDate, isDemo],
    queryFn: isDemo
      ? () => Promise.resolve({ ...DEMO_SNAPSHOT, date: snapshotDate! })
      : () => api.get(`/api/portfolio/snapshot?date=${snapshotDate}`).then(r => r.data),
    enabled:  snapshotDate !== null,
    staleTime: Infinity,
  })

  // ── Chart init (once) ────────────────────────────────────────────────────────

  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#0a0a0c' },
        textColor: '#6b6b76',
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 10,
      },
      grid:     { vertLines: { color: '#1d1d24' }, horzLines: { color: '#1d1d24' } },
      crosshair:{
        vertLine: { color: '#26262e', labelBackgroundColor: '#111114' },
        horzLine: { color: '#26262e', labelBackgroundColor: '#111114' },
      },
      rightPriceScale: { borderColor: '#26262e' },
      timeScale:       { borderColor: '#26262e', timeVisible: false },
      handleScroll:    { mouseWheel: true, pressedMouseMove: true },
      handleScale:     { mouseWheel: true, pinch: true },
      width:  containerRef.current.clientWidth,
      height: 320,
    })

    P_KEYS.forEach(key => {
      pSeriesMap.current[key] = chart.addSeries(LineSeries, {
        color: P_COLORS[key], lineWidth: 2,
        lastValueVisible: false, priceLineVisible: false,
      })
    })

    B_TICKERS.forEach(ticker => {
      bSeriesMap.current[ticker] = chart.addSeries(LineSeries, {
        color: B_COLORS[ticker], lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        lastValueVisible: false, priceLineVisible: false,
        visible: false,
      })
    })

    chartRef.current = chart

    const ro = new ResizeObserver(() => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth })
    })
    ro.observe(containerRef.current)

    const crosshairHandler = (param: Parameters<Parameters<typeof chart.subscribeCrosshairMove>[0]>[0]) => {
      if (!param.point || !param.time) return
      const pd = portDataRef.current
      if (!pd) return
      const dateStr = lwcTimeToStr(param.time)
      const idx = pd.dates.indexOf(dateStr)
      if (idx === -1) return
      setTooltip({ x: param.point.x, y: param.point.y, idx })
    }
    chart.subscribeCrosshairMove(crosshairHandler)

    return () => {
      ro.disconnect()
      chart.unsubscribeCrosshairMove(crosshairHandler)
      chart.remove()
      chartRef.current = null
      pSeriesMap.current = {}
      bSeriesMap.current = {}
    }
  }, [])

  // ── Update portfolio series ───────────────────────────────────────────────────

  useEffect(() => {
    if (!portData) return

    P_KEYS.forEach(key => {
      const series = pSeriesMap.current[key]
      if (!series) return

      const raw  = portData.series[key] ?? []
      rawPortRef.current[key] = raw

      const base = raw[0] || 1
      const values = mode === 'return'
        ? raw.map(v => ((v - base) / base) * 100)
        : raw.map(v => convert(v))

      series.setData(
        portData.dates
          .map((d, i) => ({ time: d as `${number}-${number}-${number}`, value: values[i] ?? 0 }))
          .filter(p => isFinite(p.value))
      )
      series.applyOptions({
        visible: pVis[key],
        priceFormat: mode === 'return' ? PCT_FORMAT : USD_FORMAT,
      })
    })

    chartRef.current?.timeScale().fitContent()
  }, [portData, mode, pVis, convert])

  // ── Update benchmark series ───────────────────────────────────────────────────

  useEffect(() => {
    if (!benchData) return

    benchData.benchmarks.forEach(b => {
      const ticker = b.ticker as BTicker
      const series = bSeriesMap.current[ticker]
      if (!series) return

      rawBenchRef.current[ticker] = { dates: b.dates, closes: b.closes }

      if (mode !== 'return') {
        series.applyOptions({ visible: false })
        return
      }

      const base = b.closes[0] || 1
      series.setData(
        b.dates
          .map((d, i) => ({ time: d as `${number}-${number}-${number}`, value: ((b.closes[i] - base) / base) * 100 }))
          .filter(p => isFinite(p.value))
      )
      series.applyOptions({
        visible: bVis[ticker],
        priceFormat: PCT_FORMAT,
      })
    })

    chartRef.current?.timeScale().fitContent()
  }, [benchData, mode, bVis])

  // ── Dynamic % baseline: recalculate on visible range change ──────────────────

  useEffect(() => {
    const chart = chartRef.current
    if (!chart || mode !== 'return') return

    const handler = () => {
      if (isRecalc.current || !portData) return
      const range = chart.timeScale().getVisibleRange()
      if (!range) return

      isRecalc.current = true
      const fromDate = lwcTimeToStr(range.from)

      P_KEYS.forEach(key => {
        const series = pSeriesMap.current[key]
        const raw    = rawPortRef.current[key]
        if (!series || !raw) return
        const baseIdx = Math.max(0, portData.dates.findIndex(d => d >= fromDate))
        const base    = raw[baseIdx] || 1
        series.setData(
          portData.dates
            .map((d, i) => ({ time: d as `${number}-${number}-${number}`, value: ((raw[i] - base) / base) * 100 }))
            .filter(p => isFinite(p.value))
        )
      })

      B_TICKERS.forEach(ticker => {
        const series = bSeriesMap.current[ticker]
        const rb     = rawBenchRef.current[ticker]
        if (!series || !rb || !bVis[ticker]) return
        const baseIdx = Math.max(0, rb.dates.findIndex(d => d >= fromDate))
        const base    = rb.closes[baseIdx] || 1
        series.setData(
          rb.dates
            .map((d, i) => ({ time: d as `${number}-${number}-${number}`, value: ((rb.closes[i] - base) / base) * 100 }))
            .filter(p => isFinite(p.value))
        )
      })

      isRecalc.current = false
    }

    chart.timeScale().subscribeVisibleTimeRangeChange(handler)
    return () => chart.timeScale().unsubscribeVisibleTimeRangeChange(handler)
  }, [mode, portData, bVis])

  // ── Chip helper ───────────────────────────────────────────────────────────────

  const chip = (label: string, color: string, active: boolean, dashed: boolean, onClick: () => void) => (
    <div
      onClick={onClick}
      className="trend-chip"
      style={{
        display: 'flex', alignItems: 'center', gap: 5,
        borderRadius: 5, cursor: 'pointer',
        border: `1px solid ${active ? 'var(--bdr)' : 'transparent'}`,
        background: active ? 'var(--surf2)' : 'transparent',
        color: active ? 'var(--fg1)' : 'var(--fg2)',
        fontSize: 11, userSelect: 'none', opacity: active ? 1 : 0.35,
        transition: 'opacity 120ms',
      }}
    >
      {dashed
        ? <div style={{ width: 14, height: 0, borderBottom: `2px dashed ${color}` }} />
        : <div style={{ width: 14, height: 2, background: color, borderRadius: 1 }} />
      }
      {label}
    </div>
  )

  return (
    <>
      {/* Controls: mode toggle + legend chips (mobile: each group on its own row) */}
      <div className="trend-controls" style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <div style={{
          display: 'flex', background: 'var(--surf3)', border: '1px solid var(--bdr)',
          borderRadius: 6, overflow: 'hidden',
        }}>
          {(['USD', 'return'] as const).map(m => (
            <div key={m} onClick={() => setMode(m)} style={{
              padding: '5px 10px', fontSize: 11, fontWeight: 500, cursor: 'pointer',
              color: mode === m ? 'var(--fg1)' : 'var(--fg2)',
              background: mode === m ? 'var(--surf2)' : 'transparent', userSelect: 'none',
            }}>
              {m === 'USD' ? currency : '報酬率 %'}
            </div>
          ))}
        </div>

        <div className="trend-chip-group" style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap' }}>
          {P_KEYS.map(key => chip(P_LABELS[key], P_COLORS[key], pVis[key], false, () =>
            setPVis(prev => ({ ...prev, [key]: !prev[key] }))
          ))}
        </div>

        <div className="trend-chip-group" style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap' }}>
          <div className="trend-divider" style={{ width: 1, height: 16, background: 'var(--bdr)', margin: '0 4px' }} />
          <span style={{ fontSize: 10, color: 'var(--fg3)', letterSpacing: '.5px' }}>BENCHMARK</span>
          {B_TICKERS.map(t => chip(B_LABELS[t], B_COLORS[t], mode === 'return' && bVis[t], true, () => {
            if (mode !== 'return') {
              setMode('return')
              setBVis(prev => ({ ...prev, [t]: true }))
            } else {
              setBVis(prev => ({ ...prev, [t]: !prev[t] }))
            }
          }))}
        </div>
      </div>

      {/* Chart */}
      <div style={{ position: 'relative' }} onMouseLeave={() => setTooltip(null)}>
        <div ref={containerRef} style={{ borderRadius: 6, overflow: 'hidden' }} />
        {isLoading && (
          <div style={{
            position: 'absolute', inset: 0, display: 'flex', alignItems: 'center',
            justifyContent: 'center', color: 'var(--fg3)', fontSize: 11,
            fontFamily: 'JetBrains Mono, monospace',
          }}>
            載入中...
          </div>
        )}
        {tooltip && portData && renderTooltip({
          tooltip, portData, containerRef,
          snap: snapshotData?.date === portData.dates[tooltip.idx] ? snapshotData : null,
          snapshotFetching, fmt,
        })}
      </div>

    </>
  )
}
