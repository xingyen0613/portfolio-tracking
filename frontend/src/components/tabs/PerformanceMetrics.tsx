import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'
import { useCurrency } from '../../context/CurrencyContext'
import { useDemo } from '../../context/DemoContext'
import { DEMO_HISTORY, DEMO_METRICS } from '../../data/demoData'

const P_COLORS = {
  total:    '#7c6ef5',
  crypto:   '#f0a23c',
  us_stock: '#ec5b7e',
  tw_stock: '#4ec9a8',
} as const

const P_LABELS = {
  total:    '總資產',
  crypto:   '加密貨幣',
  us_stock: '美股',
  tw_stock: '台股',
} as const

type PKey = keyof typeof P_COLORS
const P_KEYS: PKey[] = ['total', 'crypto', 'us_stock', 'tw_stock']
const WINDOWS = ['1W', '1M', '3M', '6M', '1Y', '2Y', 'YTD', 'all']

interface HistoryData {
  dates: string[]
  series: Record<string, number[]>
  latest: Record<PKey, number>
}

interface MetricsData {
  [key: string]: { total_return: number | null; sharpe: number | null; mdd: number | null }
}

function fmtPct(v: number | null) {
  if (v == null) return '—'
  return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(2)}%`
}

export default function PerformanceMetrics() {
  const { isDemo } = useDemo()
  const [win, setWin] = useState('YTD')
  const { fmt } = useCurrency()

  const { data: portData } = useQuery<HistoryData>({
    queryKey: ['portfolio/history/all'],
    queryFn: () => api.get('/api/portfolio/history?window=all').then(r => r.data),
    enabled: !isDemo,
    initialData: isDemo ? DEMO_HISTORY : undefined,
  })

  const { data: metricsData } = useQuery<MetricsData>({
    queryKey: ['portfolio/metrics', win],
    queryFn: () => api.get(`/api/portfolio/metrics?window=${win}`).then(r => r.data),
    enabled: !isDemo,
    initialData: isDemo ? DEMO_METRICS : undefined,
  })

  const winLabel = win === 'all' ? 'ALL' : win

  return (
    <div>
      <div style={{
        display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
        margin: '8px 0 12px', flexWrap: 'wrap', gap: 10,
      }}>
        <div>
          <div className="section-title">Performance Metrics</div>
          <div className="section-sub">各類別的餘額、報酬率、Sharpe 與最大回落</div>
        </div>
        <div style={{ display: 'flex', gap: 2 }}>
          {WINDOWS.map(w => (
            <div key={w} onClick={() => setWin(w)} style={{
              padding: '4px 8px', fontSize: 11, fontFamily: 'JetBrains Mono, monospace',
              color: win === w ? 'var(--accent)' : 'var(--fg-3)',
              background: win === w ? 'var(--surf-2)' : 'transparent',
              border: win === w ? '1px solid var(--bdr)' : '1px solid transparent',
              borderRadius: 5, cursor: 'pointer', userSelect: 'none',
              fontWeight: win === w ? 600 : 400,
            }}>
              {w === 'all' ? 'ALL' : w}
            </div>
          ))}
        </div>
      </div>

      <div className="perf-cards-scroll">
      <div className="perf-cards">
        {P_KEYS.map(key => {
          const color   = P_COLORS[key]
          const balance = portData?.latest[key]
          const m       = metricsData?.[key]
          const ret     = m?.total_return ?? null

          return (
            <div key={key} style={{
              background: key === 'total'
                ? 'linear-gradient(160deg, rgba(124,110,245,0.10), transparent 55%), var(--surf)'
                : 'var(--surf)',
              border: `1px solid ${key === 'total' ? 'rgba(124,110,245,0.25)' : 'var(--bdr)'}`,
              borderRadius: 10, padding: '16px 18px',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                <div style={{ width: 7, height: 7, borderRadius: '50%', background: color, flexShrink: 0 }} />
                <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--fg-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                  {P_LABELS[key]}
                </span>
              </div>
              <div style={{
                fontFamily: 'JetBrains Mono, monospace',
                fontSize: key === 'total' ? 26 : 22,
                fontWeight: 700, letterSpacing: '-0.02em',
                color, marginBottom: 14,
              }}>
                {balance != null ? fmt(balance) : '—'}
              </div>
              {[
                { label: `Return (${winLabel})`, value: fmtPct(ret),   color: ret == null ? 'var(--fg-2)' : ret >= 0 ? 'var(--c-pos)' : 'var(--c-neg)' },
                { label: 'Sharpe',               value: m?.sharpe != null ? m.sharpe.toFixed(3) : '—', color: 'var(--fg)'    },
                { label: 'Max Drawdown',          value: m?.mdd   != null ? fmtPct(m.mdd)       : '—', color: 'var(--c-neg)' },
              ].map(row => (
                <div key={row.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '3px 0' }}>
                  <span style={{ fontSize: 11, color: 'var(--fg-3)' }}>{row.label}</span>
                  <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 12, fontWeight: 500, color: row.color }}>
                    {row.value}
                  </span>
                </div>
              ))}
            </div>
          )
        })}
      </div>
      </div>
    </div>
  )
}
