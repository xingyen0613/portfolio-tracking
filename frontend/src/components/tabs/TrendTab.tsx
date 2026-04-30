import { useEffect, useRef, useState } from 'react'
import { createChart, ColorType, LineSeries, type IChartApi, type ISeriesApi } from 'lightweight-charts'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'

const COLORS = {
  total: '#58a6ff',
  crypto: '#d29922',
  us_stock: '#f85149',
  tw_stock: '#3fb950',
} as const

const LABELS = {
  total: '總資產',
  crypto: '幣圈',
  us_stock: '美股',
  tw_stock: '台股',
} as const

type Key = keyof typeof COLORS
const KEYS: Key[] = ['total', 'crypto', 'us_stock', 'tw_stock']
const WINDOWS = ['1W', '1M', '3M', '6M', '1Y', '2Y']

interface HistoryData {
  dates: string[]
  series: Record<Key, number[]>
  latest: Record<Key, number>
  metrics: Record<Key, { total_return: number | null; sharpe: number | null; mdd: number | null }>
}

function fmtUsd(v: number) {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(2)}M`
  if (v >= 1_000) return `$${(v / 1_000).toFixed(1)}k`
  return `$${v.toFixed(0)}`
}

function fmtPct(v: number | null) {
  if (v == null) return '—'
  const sign = v >= 0 ? '+' : ''
  return `${sign}${(v * 100).toFixed(2)}%`
}

export default function TrendTab() {
  const [mode, setMode] = useState<'USD' | 'return'>('USD')
  const [window, setWindow] = useState('3M')
  const [visible, setVisible] = useState<Record<Key, boolean>>({
    total: true, crypto: true, us_stock: true, tw_stock: true,
  })

  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesMap = useRef<Partial<Record<Key, ISeriesApi<'Line'>>>>({})

  const { data, isLoading } = useQuery<HistoryData>({
    queryKey: ['portfolio/history', window],
    queryFn: async () => {
      const res = await api.get(`/api/portfolio/history?window=${window}`)
      return res.data
    },
  })

  // Init chart (once)
  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#0d1117' },
        textColor: '#484f58',
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 10,
      },
      grid: {
        vertLines: { color: '#21262d' },
        horzLines: { color: '#21262d' },
      },
      crosshair: {
        vertLine: { color: '#30363d', labelBackgroundColor: '#1c2128' },
        horzLine: { color: '#30363d', labelBackgroundColor: '#1c2128' },
      },
      rightPriceScale: { borderColor: '#30363d' },
      timeScale: { borderColor: '#30363d', timeVisible: false },
      handleScroll: { mouseWheel: true, pressedMouseMove: true },
      handleScale: { mouseWheel: true, pinch: true },
      width: containerRef.current.clientWidth,
      height: 260,
    })

    KEYS.forEach(key => {
      const series = chart.addSeries(LineSeries, {
        color: COLORS[key],
        lineWidth: 2,
        lastValueVisible: false,
        priceLineVisible: false,
      })
      seriesMap.current[key] = series
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
      seriesMap.current = {}
    }
  }, [])

  // Update series data when data or mode changes
  useEffect(() => {
    if (!data) return

    KEYS.forEach(key => {
      const series = seriesMap.current[key]
      if (!series) return

      const raw = data.series[key] ?? []
      const dates = data.dates

      let values: number[]
      if (mode === 'return' && raw.length > 0) {
        const base = raw[0] || 1
        values = raw.map(v => ((v - base) / base) * 100)
      } else {
        values = raw
      }

      const chartData = dates
        .map((d, i) => ({ time: d as `${number}-${number}-${number}`, value: values[i] ?? 0 }))
        .filter(p => isFinite(p.value))

      series.setData(chartData)
      series.applyOptions({ visible: visible[key] })
    })

    chartRef.current?.timeScale().fitContent()
  }, [data, mode, visible])

  const toggleKey = (key: Key) => {
    setVisible(prev => ({ ...prev, [key]: !prev[key] }))
  }

  return (
    <>
      {/* Controls */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        {/* Mode toggle */}
        <div style={{
          display: 'flex', background: 'var(--surf3)', border: '1px solid var(--bdr)',
          borderRadius: 6, overflow: 'hidden',
        }}>
          {(['USD', 'return'] as const).map(m => (
            <div
              key={m}
              onClick={() => setMode(m)}
              style={{
                padding: '5px 10px', fontSize: 11, fontWeight: 500, cursor: 'pointer',
                color: mode === m ? 'var(--fg1)' : 'var(--fg2)',
                background: mode === m ? 'var(--surf2)' : 'transparent',
                userSelect: 'none',
              }}
            >
              {m === 'USD' ? 'USD' : '報酬率 %'}
            </div>
          ))}
        </div>

        {/* Time window */}
        <div style={{ display: 'flex', gap: 2 }}>
          {WINDOWS.map(w => (
            <div
              key={w}
              onClick={() => setWindow(w)}
              style={{
                padding: '5px 7px', fontSize: 11, fontFamily: 'JetBrains Mono, monospace',
                color: window === w ? 'var(--blue)' : 'var(--fg2)',
                background: window === w ? 'var(--surf2)' : 'transparent',
                border: window === w ? '1px solid var(--bdr)' : '1px solid transparent',
                borderRadius: 4, cursor: 'pointer', userSelect: 'none',
              }}
            >
              {w}
            </div>
          ))}
        </div>
      </div>

      {/* Legend chips */}
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
        {KEYS.map(key => (
          <div
            key={key}
            onClick={() => toggleKey(key)}
            style={{
              display: 'flex', alignItems: 'center', gap: 5,
              padding: '4px 8px', borderRadius: 5, cursor: 'pointer',
              border: `1px solid ${visible[key] ? 'var(--bdr)' : 'transparent'}`,
              background: visible[key] ? 'var(--surf2)' : 'transparent',
              color: visible[key] ? 'var(--fg1)' : 'var(--fg2)',
              fontSize: 11, userSelect: 'none', opacity: visible[key] ? 1 : 0.35,
              transition: 'opacity 120ms',
            }}
          >
            <div style={{ width: 14, height: 2, background: COLORS[key], borderRadius: 1 }} />
            {LABELS[key]}
          </div>
        ))}
      </div>

      {/* Chart container */}
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

      {/* Stat row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
        {KEYS.map(key => {
          const latest = data?.latest[key]
          const m = data?.metrics[key]
          const ret = m?.total_return ?? null
          const isUp = ret != null ? ret >= 0 : null
          return (
            <div
              key={key}
              style={{
                background: 'var(--surf)', border: '1px solid var(--bdr)',
                borderTop: `2px solid ${COLORS[key]}`,
                borderRadius: 8, padding: '10px 12px',
              }}
            >
              <div style={{
                fontSize: 10, color: 'var(--fg2)', textTransform: 'uppercase',
                letterSpacing: '.5px', marginBottom: 5,
                display: 'flex', alignItems: 'center', gap: 5,
              }}>
                <div style={{ width: 5, height: 5, borderRadius: '50%', background: COLORS[key] }} />
                {LABELS[key]}
              </div>
              <div style={{
                fontFamily: 'JetBrains Mono, monospace', fontSize: 15, fontWeight: 500,
                color: 'var(--fg1)',
              }}>
                {latest != null ? fmtUsd(latest) : '—'}
              </div>
              <div style={{
                fontFamily: 'JetBrains Mono, monospace', fontSize: 11, marginTop: 3,
                color: isUp === null ? 'var(--fg2)' : isUp ? 'var(--green)' : 'var(--red)',
              }}>
                {fmtPct(ret)}
              </div>
            </div>
          )
        })}
      </div>
    </>
  )
}
