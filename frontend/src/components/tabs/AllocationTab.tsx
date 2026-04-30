import { useEffect, useRef, useState } from 'react'
import { createChart, ColorType, LineSeries, type IChartApi } from 'lightweight-charts'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'

// ── Constants ────────────────────────────────────────────────────────────────

const P_COLORS: Record<string, string> = {
  total:    '#58a6ff',
  crypto:   '#d29922',
  us_stock: '#f85149',
  tw_stock: '#3fb950',
}
const P_LABELS: Record<string, string> = {
  total: '總資產', crypto: '幣圈', us_stock: '美股', tw_stock: '台股',
}

// ── Types ─────────────────────────────────────────────────────────────────────

interface Category   { key: string; label: string; value_usd: number; pct: number }
interface DrillItem  { symbol: string; value_usd: number; pct: number }
interface AllocData  { total: number; categories: Category[] }
interface DrillData  { category: string; label: string; items: DrillItem[] }
interface MetricsMap { [key: string]: { total_return: number | null; sharpe: number | null; mdd: number | null } }
interface HistoryData{ dates: string[]; series: Record<string, number[]> }

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtUsd(v: number) {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(2)}M`
  if (v >= 1_000)     return `$${(v / 1_000).toFixed(1)}k`
  return `$${v.toFixed(0)}`
}

function fmtPct(v: number | null, mul = true) {
  if (v == null) return '—'
  const val = mul ? v * 100 : v
  return `${val >= 0 ? '+' : ''}${val.toFixed(2)}%`
}

// ── SVG Donut ─────────────────────────────────────────────────────────────────

function Donut({ slices, size = 120 }: { slices: { v: number; color: string }[]; size?: number }) {
  const r = 44, cx = size / 2, cy = size / 2
  const total = slices.reduce((s, d) => s + d.v, 0)
  let ang = -Math.PI / 2
  return (
    <svg width={size} height={size}>
      {slices.map((d, i) => {
        const a  = (d.v / total) * Math.PI * 2
        const x1 = cx + r * Math.cos(ang), y1 = cy + r * Math.sin(ang)
        ang += a
        const x2 = cx + r * Math.cos(ang), y2 = cy + r * Math.sin(ang)
        return (
          <path key={i}
            d={`M${cx},${cy} L${x1.toFixed(2)},${y1.toFixed(2)} A${r},${r} 0 ${a > Math.PI ? 1 : 0},1 ${x2.toFixed(2)},${y2.toFixed(2)} Z`}
            fill={d.color} opacity={0.88}
          />
        )
      })}
      <circle cx={cx} cy={cy} r={28} fill="var(--surf)" />
    </svg>
  )
}

// ── Mini Chart ────────────────────────────────────────────────────────────────

function MiniChart({ histData }: { histData: HistoryData | undefined }) {
  const ref       = useRef<HTMLDivElement>(null)
  const chartRef  = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ReturnType<IChartApi['addSeries']> | null>(null)

  useEffect(() => {
    if (!ref.current) return
    const c = createChart(ref.current, {
      layout: { background: { type: ColorType.Solid, color: '#0d1117' }, textColor: '#484f58', fontSize: 9, fontFamily: 'JetBrains Mono, monospace' },
      grid: { vertLines: { color: '#21262d' }, horzLines: { color: '#21262d' } },
      crosshair: { vertLine: { color: '#30363d', labelBackgroundColor: '#1c2128' }, horzLine: { color: '#30363d', labelBackgroundColor: '#1c2128' } },
      rightPriceScale: { borderColor: '#30363d' },
      timeScale: { borderColor: '#30363d', timeVisible: false },
      handleScroll: { mouseWheel: true, pressedMouseMove: true },
      handleScale:  { mouseWheel: true, pinch: true },
      width: ref.current.clientWidth, height: 180,
    })
    seriesRef.current = c.addSeries(LineSeries, {
      color: P_COLORS.total, lineWidth: 2, lastValueVisible: false, priceLineVisible: false,
    })
    chartRef.current = c

    const ro = new ResizeObserver(() => {
      if (ref.current) c.applyOptions({ width: ref.current.clientWidth })
    })
    ro.observe(ref.current)
    return () => { ro.disconnect(); c.remove(); chartRef.current = null; seriesRef.current = null }
  }, [])

  useEffect(() => {
    if (!histData || !seriesRef.current) return
    const chartData = histData.dates.map((d, i) => ({
      time: d as `${number}-${number}-${number}`,
      value: histData.series.total?.[i] ?? 0,
    })).filter(p => isFinite(p.value))
    seriesRef.current.setData(chartData)
    chartRef.current?.timeScale().fitContent()
  }, [histData])

  return <div ref={ref} style={{ borderRadius: 6, overflow: 'hidden' }} />
}

// ── Main Component ────────────────────────────────────────────────────────────

const WINDOWS = ['1W', '1M', '3M', '6M', '1Y', '2Y', 'YTD', 'all']

export default function AllocationTab() {
  const [drill, setDrill] = useState<string | null>(null)
  const [win, setWin]     = useState('YTD')

  const { data: allocData } = useQuery<AllocData>({
    queryKey: ['portfolio/allocation'],
    queryFn: () => api.get('/api/portfolio/allocation').then(r => r.data),
  })

  const { data: drillData } = useQuery<DrillData>({
    queryKey: ['portfolio/allocation/drill', drill],
    queryFn: () => api.get(`/api/portfolio/allocation/${drill}`).then(r => r.data),
    enabled: drill !== null,
  })

  const { data: metricsData } = useQuery<MetricsMap>({
    queryKey: ['portfolio/metrics', win],
    queryFn: () => api.get(`/api/portfolio/metrics?window=${win}`).then(r => r.data),
  })

  const { data: histData } = useQuery<HistoryData>({
    queryKey: ['portfolio/history/all'],
    queryFn: () => api.get('/api/portfolio/history?window=all').then(r => r.data),
  })

  // Donut slices
  const categories = allocData?.categories ?? []
  const donutSlices = drill && drillData
    ? drillData.items.slice(0, 8).map((item, i) => ({
        v: item.value_usd,
        color: `hsl(${(i * 47 + 30) % 360}, 60%, 55%)`,
      }))
    : categories.map(c => ({ v: c.value_usd, color: P_COLORS[c.key] ?? '#888' }))

  const legendItems = drill && drillData
    ? drillData.items.slice(0, 8).map((item, i) => ({
        label: item.symbol,
        pct: item.pct,
        color: `hsl(${(i * 47 + 30) % 360}, 60%, 55%)`,
        canDrill: false,
      }))
    : categories.map(c => ({
        label: c.label,
        pct: c.pct,
        color: P_COLORS[c.key] ?? '#888',
        canDrill: true,
        key: c.key,
      }))

  const metricKeys = ['total', 'crypto', 'us_stock', 'tw_stock']

  return (
    <>
      {/* Two-column: Donut + Mini chart */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>

        {/* Donut */}
        <div style={{
          background: 'var(--surf)', border: '1px solid var(--bdr)', borderRadius: 8, padding: 14,
        }}>
          <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--fg2)', textTransform: 'uppercase', letterSpacing: '.5px', marginBottom: 12 }}>
            {drill && drillData ? (
              <span>
                <span
                  onClick={() => setDrill(null)}
                  style={{ color: 'var(--blue)', cursor: 'pointer' }}
                >
                  ← 返回
                </span>
                {' '}{drillData.label} 持倉佔比
              </span>
            ) : '資產類別佔比'}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            {donutSlices.length > 0 && <Donut slices={donutSlices} size={118} />}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 9, flex: 1 }}>
              {legendItems.map((item, i) => (
                <div
                  key={i}
                  onClick={() => (item as any).canDrill && setDrill((item as any).key)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 7,
                    cursor: (item as any).canDrill ? 'pointer' : 'default',
                  }}
                >
                  <div style={{ width: 7, height: 7, borderRadius: '50%', background: item.color, flexShrink: 0 }} />
                  <span style={{ fontSize: 12, color: 'var(--fg2)', flex: 1 }}>{item.label}</span>
                  <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 12 }}>{item.pct}%</span>
                  {(item as any).canDrill && <span style={{ fontSize: 10, color: 'var(--fg3)' }}>↗</span>}
                </div>
              ))}
              {!drill && <div style={{ fontSize: 10, color: 'var(--fg3)', marginTop: 4 }}>點選可展開</div>}
            </div>
          </div>
        </div>

        {/* Mini chart */}
        <div style={{
          background: 'var(--surf)', border: '1px solid var(--bdr)', borderRadius: 8, padding: 14,
        }}>
          <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--fg2)', textTransform: 'uppercase', letterSpacing: '.5px', marginBottom: 12 }}>
            資產走勢（全部）
          </div>
          <MiniChart histData={histData} />
          {histData && (
            <div style={{ marginTop: 8, fontSize: 11, color: 'var(--fg2)', fontFamily: 'JetBrains Mono, monospace' }}>
              {fmtUsd(histData.series.total?.slice(-1)[0] ?? 0)}{' '}
              <span style={{ color: 'var(--green)' }}>
                {(() => {
                  const arr = histData.series.total ?? []
                  if (arr.length < 2) return ''
                  const ret = (arr[arr.length - 1] - arr[0]) / arr[0] * 100
                  return `${ret >= 0 ? '+' : ''}${ret.toFixed(1)}%`
                })()}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Metrics grid */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--fg3)', textTransform: 'uppercase', letterSpacing: '.6px' }}>
          績效指標
        </div>
        <div style={{ display: 'flex', gap: 2 }}>
          {WINDOWS.map(w => (
            <div key={w} onClick={() => setWin(w)} style={{
              padding: '3px 6px', fontSize: 10, fontFamily: 'JetBrains Mono, monospace',
              color: win === w ? 'var(--blue)' : 'var(--fg3)',
              background: win === w ? 'var(--surf2)' : 'transparent',
              border: win === w ? '1px solid var(--bdr)' : '1px solid transparent',
              borderRadius: 4, cursor: 'pointer', userSelect: 'none',
            }}>
              {w === 'all' ? 'ALL' : w}
            </div>
          ))}
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        {metricKeys.map(key => {
          const m = metricsData?.[key]
          const ret = m?.total_return ?? null
          return (
            <div key={key} style={{
              background: 'var(--surf)', border: '1px solid var(--bdr)', borderRadius: 8, padding: '11px 13px',
            }}>
              <div style={{
                fontSize: 10, fontWeight: 600, color: 'var(--fg2)', marginBottom: 9,
                display: 'flex', alignItems: 'center', gap: 5,
              }}>
                <div style={{ width: 5, height: 5, borderRadius: '50%', background: P_COLORS[key] ?? P_COLORS.total }} />
                {P_LABELS[key]}
              </div>
              {[
                { label: '報酬率', value: ret != null ? fmtPct(ret) : '—', color: ret == null ? 'var(--fg1)' : ret >= 0 ? 'var(--green)' : 'var(--red)' },
                { label: 'Sharpe', value: m?.sharpe != null ? m.sharpe.toFixed(2) : '—', color: 'var(--fg1)' },
                { label: 'MDD',    value: m?.mdd != null ? fmtPct(m.mdd) : '—',    color: 'var(--red)' },
              ].map(row => (
                <div key={row.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 5 }}>
                  <span style={{ fontSize: 11, color: 'var(--fg3)' }}>{row.label}</span>
                  <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 12, color: row.color }}>{row.value}</span>
                </div>
              ))}
            </div>
          )
        })}
      </div>
    </>
  )
}
