import { useEffect, useRef, useState } from 'react'
import {
  createChart, ColorType, LineSeries, LineStyle,
  type IChartApi, type ISeriesApi,
} from 'lightweight-charts'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'

// ── Portfolio constants ──────────────────────────────────────────────────────

const P_COLORS = { total: '#58a6ff', crypto: '#d29922', us_stock: '#f85149', tw_stock: '#3fb950' } as const
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

const WINDOWS = ['1W', '1M', '3M', '6M', '1Y', '2Y', 'all']

// ── Types ─────────────────────────────────────────────────────────────────────

interface HistoryData {
  dates: string[]
  series: Record<PKey, number[]>
  latest: Record<PKey, number>
  metrics: Record<PKey, { total_return: number | null; sharpe: number | null; mdd: number | null }>
}

interface MetricsData {
  [key: string]: { total_return: number | null; sharpe: number | null; mdd: number | null }
}

interface BenchmarkSeries { ticker: string; label: string; color: string; dates: string[]; closes: number[] }
interface BenchmarkData { benchmarks: BenchmarkSeries[] }

// ── Formatters ────────────────────────────────────────────────────────────────

function fmtUsd(v: number) {
  const abs = Math.abs(v)
  const sign = v < 0 ? '-' : ''
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(2)}M`
  if (abs >= 1_000) return `${sign}$${(abs / 1_000).toFixed(1)}k`
  return `${sign}$${abs.toFixed(0)}`
}

function fmtPct(v: number | null) {
  if (v == null) return '—'
  return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(2)}%`
}

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

// ── Component ─────────────────────────────────────────────────────────────────

export default function TrendTab() {
  const [mode, setMode] = useState<'USD' | 'return'>('USD')
  const [win, setWin]   = useState('3M')
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

  // ── Data queries ─────────────────────────────────────────────────────────────
  // 圖表永遠顯示全部資料，win 只控制下方 stat cards 的收益計算區間

  const { data: portData, isLoading } = useQuery<HistoryData>({
    queryKey: ['portfolio/history/all'],
    queryFn: () => api.get('/api/portfolio/history?window=all').then(r => r.data),
  })

  const { data: metricsData } = useQuery<MetricsData>({
    queryKey: ['portfolio/metrics', win],
    queryFn: () => api.get(`/api/portfolio/metrics?window=${win}`).then(r => r.data),
  })

  const { data: benchData } = useQuery<BenchmarkData>({
    queryKey: ['benchmarks/all'],
    queryFn: () =>
      api.get('/api/benchmarks?tickers=%5EGSPC,0050.TW,BTC-USD&start=2015-01-01').then(r => r.data),
  })

  // ── Chart init (once) ────────────────────────────────────────────────────────

  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#0d1117' },
        textColor: '#484f58',
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 10,
      },
      grid:     { vertLines: { color: '#21262d' }, horzLines: { color: '#21262d' } },
      crosshair:{
        vertLine: { color: '#30363d', labelBackgroundColor: '#1c2128' },
        horzLine: { color: '#30363d', labelBackgroundColor: '#1c2128' },
      },
      rightPriceScale: { borderColor: '#30363d' },
      timeScale:       { borderColor: '#30363d', timeVisible: false },
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

    return () => {
      ro.disconnect()
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
        : raw

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
  }, [portData, mode, pVis])

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
      style={{
        display: 'flex', alignItems: 'center', gap: 5,
        padding: '4px 8px', borderRadius: 5, cursor: 'pointer',
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

  const winLabel = win === 'all' ? '全部' : win

  return (
    <>
      {/* Controls: mode toggle + legend chips */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
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
              {m === 'USD' ? 'USD' : '報酬率 %'}
            </div>
          ))}
        </div>

        {P_KEYS.map(key => chip(P_LABELS[key], P_COLORS[key], pVis[key], false, () =>
          setPVis(prev => ({ ...prev, [key]: !prev[key] }))
        ))}

        <div style={{ width: 1, height: 16, background: 'var(--bdr)', margin: '0 4px' }} />
        <span style={{ fontSize: 10, color: 'var(--fg3)', letterSpacing: '.5px' }}>BENCHMARK</span>
        {B_TICKERS.map(t => chip(B_LABELS[t], B_COLORS[t], bVis[t], true, () => {
          if (mode !== 'return') {
            setMode('return')
            setBVis(prev => ({ ...prev, [t]: true }))
          } else {
            setBVis(prev => ({ ...prev, [t]: !prev[t] }))
          }
        }))}
      </div>

      {/* Chart */}
      <div style={{ position: 'relative' }}>
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
      </div>

      {/* Window selector — controls stat card metrics below */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 10, color: 'var(--fg3)', letterSpacing: '.4px' }}>收益計算區間</span>
        <div style={{ display: 'flex', gap: 2 }}>
          {WINDOWS.map(w => (
            <div key={w} onClick={() => setWin(w)} style={{
              padding: '4px 7px', fontSize: 11, fontFamily: 'JetBrains Mono, monospace',
              color: win === w ? 'var(--blue)' : 'var(--fg2)',
              background: win === w ? 'var(--surf2)' : 'transparent',
              border: win === w ? '1px solid var(--bdr)' : '1px solid transparent',
              borderRadius: 4, cursor: 'pointer', userSelect: 'none',
            }}>
              {w === 'all' ? 'ALL' : w}
            </div>
          ))}
        </div>
      </div>

      {/* Stat cards — latest value + return for selected window */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
        {P_KEYS.map(key => {
          const latest = portData?.latest[key]
          const ret    = metricsData?.[key]?.total_return ?? null
          return (
            <div key={key} style={{
              background: 'var(--surf)', border: '1px solid var(--bdr)',
              borderTop: `2px solid ${P_COLORS[key]}`, borderRadius: 8, padding: '10px 12px',
            }}>
              <div style={{
                fontSize: 10, color: 'var(--fg2)', textTransform: 'uppercase',
                letterSpacing: '.5px', marginBottom: 5,
                display: 'flex', alignItems: 'center', gap: 5,
              }}>
                <div style={{ width: 5, height: 5, borderRadius: '50%', background: P_COLORS[key] }} />
                {P_LABELS[key]}
              </div>
              <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 15, fontWeight: 500 }}>
                {latest != null ? fmtUsd(latest) : '—'}
              </div>
              <div style={{
                fontFamily: 'JetBrains Mono, monospace', fontSize: 11, marginTop: 3,
                color: ret == null ? 'var(--fg2)' : ret >= 0 ? 'var(--green)' : 'var(--red)',
              }}>
                {fmtPct(ret)}
                <span style={{ color: 'var(--fg3)', marginLeft: 4 }}>{winLabel}</span>
              </div>
            </div>
          )
        })}
      </div>
    </>
  )
}
