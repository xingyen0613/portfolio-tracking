import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'

// ── Types ─────────────────────────────────────────────────────────────────────

interface HoldingRow  { symbol: string; name: string; quantity: string; price: string; value_usd: number }
interface Section     { label: string; total_usd: number; rows: HoldingRow[] }
interface Platform    { name: string; display: string; abbr: string; color: string; fg: string; category: string; total_usd: number; sections: Section[] }
interface Summary     { total_usd: number; crypto_usd?: number; us_stock_usd?: number; tw_stock_usd?: number }
interface HoldingsData{ summary: Summary; platforms: Platform[] }

// ── Constants ─────────────────────────────────────────────────────────────────

const CAT_COLORS = { crypto: '#d29922', us_stock: '#f85149', tw_stock: '#3fb950', total: '#58a6ff' }

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtUsd(v: number) {
  if (!isFinite(v)) return '—'
  const abs = Math.abs(v)
  const sign = v < 0 ? '-' : ''
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(2)}M`
  if (abs >= 1_000)     return `${sign}$${(abs / 1_000).toFixed(1)}k`
  return `${sign}$${abs.toFixed(0)}`
}

// ── Chevron icon ──────────────────────────────────────────────────────────────

function Chevron({ open }: { open: boolean }) {
  return (
    <svg width={14} height={14} viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth={1.5}
      style={{ transform: open ? 'rotate(90deg)' : 'none', transition: 'transform 150ms', flexShrink: 0, color: 'var(--fg3)' }}>
      <path d="M5 3l4 4-4 4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

// ── Platform card ─────────────────────────────────────────────────────────────

function PlatformCard({ p }: { p: Platform }) {
  const [open, setOpen] = useState(p.total_usd > 10_000)

  return (
    <div style={{ background: 'var(--surf)', border: '1px solid var(--bdr)', borderRadius: 8, overflow: 'hidden' }}>
      {/* Header */}
      <div
        onClick={() => setOpen(o => !o)}
        style={{
          display: 'flex', alignItems: 'center', gap: 10, padding: '11px 14px', cursor: 'pointer',
          borderBottom: open ? '1px solid var(--bdr2)' : 'none',
        }}
        onMouseEnter={e => (e.currentTarget.style.background = 'var(--surf2)')}
        onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
      >
        <div style={{
          width: 26, height: 26, borderRadius: 5, display: 'flex', alignItems: 'center',
          justifyContent: 'center', fontSize: 10, fontWeight: 700, flexShrink: 0,
          background: p.color, color: p.fg,
        }}>
          {p.abbr}
        </div>
        <div style={{ fontSize: 13, fontWeight: 600 }}>{p.display}</div>
        <div style={{
          marginLeft: 'auto', fontFamily: 'JetBrains Mono, monospace', fontSize: 13,
          color: p.total_usd < 0 ? 'var(--red)' : 'var(--fg1)',
        }}>
          {fmtUsd(p.total_usd)}
        </div>
        <Chevron open={open} />
      </div>

      {/* Sections */}
      {open && (
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              {['代碼', '數量', '單價', '市值'].map((h, i) => (
                <th key={h} style={{
                  padding: '7px 14px', fontSize: 10, color: 'var(--fg3)', fontWeight: 500,
                  textAlign: i === 0 ? 'left' : 'right',
                  borderBottom: '1px solid var(--bdr2)', letterSpacing: '.4px',
                }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {p.sections.map(sec => (
              <>
                {/* Section divider */}
                <tr key={`sec-${sec.label}`}>
                  <td colSpan={4} style={{ padding: 0 }}>
                    <div style={{
                      padding: '5px 14px', fontSize: 10, fontWeight: 600, color: 'var(--fg3)',
                      background: 'var(--bg)', textTransform: 'uppercase', letterSpacing: '.5px',
                      display: 'flex', alignItems: 'center', gap: 8,
                    }}>
                      {sec.label}
                      <span style={{ marginLeft: 'auto', fontFamily: 'JetBrains Mono, monospace', color: 'var(--fg2)' }}>
                        {fmtUsd(sec.total_usd)}
                      </span>
                    </div>
                  </td>
                </tr>

                {/* Holdings rows */}
                {sec.rows.map((row, i) => (
                  <tr key={i}
                    onMouseEnter={e => { Array.from(e.currentTarget.cells).forEach(c => (c.style.background = 'var(--surf2)')) }}
                    onMouseLeave={e => { Array.from(e.currentTarget.cells).forEach(c => (c.style.background = '')) }}
                  >
                    <td style={{ padding: '8px 14px', fontSize: 12, borderBottom: '1px solid var(--bdr2)' }}>
                      <span style={{
                        display: 'inline-block', background: 'var(--surf3)', border: '1px solid var(--bdr)',
                        borderRadius: 4, padding: '2px 5px', fontFamily: 'JetBrains Mono, monospace', fontSize: 11, fontWeight: 500,
                      }}>
                        {row.symbol}
                      </span>
                    </td>
                    {[row.quantity, row.price].map((v, j) => (
                      <td key={j} style={{
                        padding: '8px 14px', fontSize: 12, textAlign: 'right',
                        fontFamily: 'JetBrains Mono, monospace', borderBottom: '1px solid var(--bdr2)',
                        color: 'var(--fg2)',
                      }}>
                        {v}
                      </td>
                    ))}
                    <td style={{
                      padding: '8px 14px', fontSize: 12, textAlign: 'right',
                      fontFamily: 'JetBrains Mono, monospace', borderBottom: '1px solid var(--bdr2)',
                      color: row.value_usd < 0 ? 'var(--red)' : 'var(--fg1)',
                    }}>
                      {fmtUsd(row.value_usd)}
                    </td>
                  </tr>
                ))}
              </>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function HoldingsTab() {
  const { data, isLoading } = useQuery<HoldingsData>({
    queryKey: ['holdings'],
    queryFn: () => api.get('/api/holdings').then(r => r.data),
  })

  if (isLoading) {
    return (
      <div style={{ color: 'var(--fg3)', fontSize: 11, padding: 24, textAlign: 'center', fontFamily: 'JetBrains Mono, monospace' }}>
        載入中...
      </div>
    )
  }

  const summary  = data?.summary
  const platforms = data?.platforms ?? []

  const statCards = [
    { key: 'total',    label: '總資產', val: summary?.total_usd,    sub: summary ? `NT$${((summary.total_usd ?? 0) * 31.5).toLocaleString('en', { maximumFractionDigits: 0 })}` : undefined },
    { key: 'crypto',   label: '幣圈',   val: summary?.crypto_usd },
    { key: 'us_stock', label: '美股',   val: summary?.us_stock_usd },
    { key: 'tw_stock', label: '台股',   val: summary?.tw_stock_usd },
  ]

  return (
    <>
      {/* Stat cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
        {statCards.map(s => {
          const color = CAT_COLORS[s.key as keyof typeof CAT_COLORS] ?? CAT_COLORS.total
          return (
            <div key={s.key} style={{
              background: 'var(--surf)', border: '1px solid var(--bdr)',
              borderTop: `2px solid ${color}`, borderRadius: 8, padding: '12px 14px',
            }}>
              <div style={{ fontSize: 10, color: 'var(--fg2)', textTransform: 'uppercase', letterSpacing: '.5px', marginBottom: 5, display: 'flex', alignItems: 'center', gap: 5 }}>
                <div style={{ width: 5, height: 5, borderRadius: '50%', background: color }} />
                {s.label}
              </div>
              <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 17, fontWeight: 500, color }}>
                {s.val != null ? fmtUsd(s.val) : '—'}
              </div>
              {s.sub && <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, marginTop: 3, color: 'var(--fg3)' }}>{s.sub}</div>}
            </div>
          )
        })}
      </div>

      {/* Section label */}
      <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--fg3)', textTransform: 'uppercase', letterSpacing: '.6px' }}>
        持倉明細
      </div>

      {/* Platform cards */}
      {platforms.map(p => <PlatformCard key={p.name} p={p} />)}
    </>
  )
}
