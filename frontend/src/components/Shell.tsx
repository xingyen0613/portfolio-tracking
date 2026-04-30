import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import HoldingsTab from './tabs/HoldingsTab'
import AllocationTab from './tabs/AllocationTab'
import TrendTab from './tabs/TrendTab'

interface MetaData { last_updated: string | null; usd_twd_rate: number }

const TABS = ['持倉明細', '資產配置', '資產走勢'] as const

export default function Shell() {
  const [activeTab, setActiveTab] = useState<number>(2)

  const { data: meta } = useQuery<MetaData>({
    queryKey: ['portfolio/meta'],
    queryFn: () => api.get('/api/portfolio/meta').then(r => r.data),
    staleTime: 5 * 60 * 1000,
  })

  const content = [<HoldingsTab />, <AllocationTab />, <TrendTab />]

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', height: '100vh',
      background: 'var(--bg)', color: 'var(--fg1)',
      fontFamily: "'Plus Jakarta Sans', sans-serif",
    }}>
      {/* Topbar */}
      <div style={{
        height: 48, background: 'var(--surf)', borderBottom: '1px solid var(--bdr)',
        display: 'flex', alignItems: 'center', padding: '0 18px', gap: 16, flexShrink: 0,
      }}>
        <div style={{ fontSize: 14, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 7 }}>
          <div style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--blue)' }} />
          Portfolio
        </div>
        <div style={{
          marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 14,
          fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: 'var(--fg2)',
        }}>
          {meta?.last_updated && (
            <span style={{ color: 'var(--fg3)' }}>
              更新：{meta.last_updated}
            </span>
          )}
          <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <span style={{
              width: 5, height: 5, borderRadius: '50%', background: 'var(--green)',
              boxShadow: '0 0 6px var(--green)', display: 'inline-block',
            }} />
            LIVE
          </span>
          <span style={{ color: 'var(--fg3)' }}>
            1 USD = {meta?.usd_twd_rate?.toFixed(1) ?? '31.5'} TWD
          </span>
        </div>
      </div>

      {/* Tabs */}
      <div style={{
        display: 'flex', background: 'var(--surf)', borderBottom: '1px solid var(--bdr)',
        padding: '0 18px', flexShrink: 0,
      }}>
        {TABS.map((tab, i) => (
          <div
            key={tab}
            onClick={() => setActiveTab(i)}
            style={{
              padding: '9px 14px', fontSize: 12, fontWeight: 500, cursor: 'pointer',
              color: activeTab === i ? 'var(--fg1)' : 'var(--fg2)',
              borderBottom: activeTab === i ? '2px solid var(--blue)' : '2px solid transparent',
              userSelect: 'none',
            }}
          >
            {tab}
          </div>
        ))}
      </div>

      {/* Content */}
      <div style={{
        flex: 1, minHeight: 0, overflowY: 'auto', padding: '16px 18px',
        display: 'flex', flexDirection: 'column', gap: 12,
      }}>
        {content[activeTab]}
      </div>
    </div>
  )
}
