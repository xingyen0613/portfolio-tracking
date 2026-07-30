import { useQuery } from '@tanstack/react-query'
import PerformanceMetrics from '../components/tabs/PerformanceMetrics'
import HoldingsTab from '../components/tabs/HoldingsTab'
import AllocationTab from '../components/tabs/AllocationTab'
import TrendTab from '../components/tabs/TrendTab'
import EmptyState from '../components/EmptyState'
import { listConnectors } from '../api/connectors'
import { api } from '../api/client'
import { useDemo } from '../context/DemoContext'
import { DEMO_CONNECTORS, DEMO_HISTORY } from '../data/demoData'
import type { ModalState } from '../App'

interface Props {
  openModal: (m: ModalState) => void
}

export default function DashboardTab({ openModal }: Props) {
  const { isDemo } = useDemo()
  const { data: connectors, isLoading } = useQuery({
    queryKey: ['connectors'],
    queryFn: listConnectors,
    enabled: !isDemo,
    initialData: isDemo ? DEMO_CONNECTORS : undefined,
  })

  // 共用 PerformanceMetrics / TrendTab 的 history query key，react-query 會 dedupe
  const { isLoading: historyLoading } = useQuery({
    queryKey: ['portfolio/history/all'],
    queryFn: () => api.get('/api/portfolio/history?window=all').then(r => r.data),
    enabled: !isDemo,
    initialData: isDemo ? DEMO_HISTORY : undefined,
  })

  if (isLoading || historyLoading) {
    return (
      <div className="dashboard-loading">
        <div className="spinner" />
        <div className="load-label">載入您的資產中…</div>
      </div>
    )
  }

  if (!isLoading && connectors && connectors.length === 0) {
    return (
      <EmptyState
        icon="plug"
        title="連接您的第一個來源"
        description="新增交易所、錢包或券商，開始在同一處追蹤您的資產。資料每天自動同步。"
        ctaLabel="新增資料來源"
        onCta={() => openModal({ kind: 'addSource' })}
      />
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>
      <section data-tour="perf-metrics">
        <PerformanceMetrics />
      </section>

      <section data-tour="asset-trend">
        <div className="section-head">
          <div>
            <div className="section-title">Asset Trend</div>
            <div className="section-sub">各類別的歷史資產走勢</div>
          </div>
        </div>
        <TrendTab />
      </section>

      <section data-tour="allocation">
        <div className="section-head">
          <div>
            <div className="section-title">Allocation</div>
            <div className="section-sub">點擊任一類別可查看主要持倉明細</div>
          </div>
        </div>
        <AllocationTab />
      </section>

      <section data-tour="holdings">
        <div className="section-head">
          <div>
            <div className="section-title">Holdings by Source</div>
            <div className="section-sub">點擊任一平台可展開明細</div>
          </div>
        </div>
        <HoldingsTab onAddSource={() => openModal({ kind: 'addSource' })} />
      </section>
    </div>
  )
}
