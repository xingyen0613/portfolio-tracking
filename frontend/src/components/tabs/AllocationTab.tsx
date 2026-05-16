import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'

// ── Constants ────────────────────────────────────────────────────────────────

const P_COLORS: Record<string, string> = {
  total:    '#7c6ef5',
  crypto:   '#f0a23c',
  us_stock: '#ec5b7e',
  tw_stock: '#4ec9a8',
}
const P_LABELS: Record<string, string> = {
  total: '總資產', crypto: '幣圈', us_stock: '美股', tw_stock: '台股',
}

// ── Types ─────────────────────────────────────────────────────────────────────

interface Category   { key: string; label: string; value_usd: number; pct: number }
interface DrillItem  { symbol: string; value_usd: number; pct: number }
interface AllocData  { total: number; categories: Category[] }
interface DrillData  { category: string; label: string; items: DrillItem[] }

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

// ── Main Component ────────────────────────────────────────────────────────────

export default function AllocationTab() {
  const [drill, setDrill] = useState<string | null>(null)

  const { data: allocData } = useQuery<AllocData>({
    queryKey: ['portfolio/allocation'],
    queryFn: () => api.get('/api/portfolio/allocation').then(r => r.data),
  })

  const { data: drillData } = useQuery<DrillData>({
    queryKey: ['portfolio/allocation/drill', drill],
    queryFn: () => api.get(`/api/portfolio/allocation/${drill}`).then(r => r.data),
    enabled: drill !== null,
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

  return (
    <div style={{ background: 'var(--surf)', border: '1px solid var(--bdr)', borderRadius: 8, padding: 14 }}>
      <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--fg2)', textTransform: 'uppercase', letterSpacing: '.5px', marginBottom: 12 }}>
        {drill && drillData ? (
          <span>
            <span onClick={() => setDrill(null)} style={{ color: 'var(--blue)', cursor: 'pointer' }}>
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
              style={{ display: 'flex', alignItems: 'center', gap: 7, cursor: (item as any).canDrill ? 'pointer' : 'default' }}
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
  )
}
