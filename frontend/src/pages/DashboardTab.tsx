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
        <div className="load-label">Loading your portfolio…</div>
      </div>
    )
  }

  if (!isLoading && connectors && connectors.length === 0) {
    return (
      <EmptyState
        icon="plug"
        title="Connect your first source"
        description="Add an exchange, wallet or broker to start tracking your portfolio in one place. Your data syncs automatically every day."
        ctaLabel="Add a data source"
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
            <div className="section-sub">Historical value across categories</div>
          </div>
        </div>
        <TrendTab />
      </section>

      <section data-tour="allocation">
        <div className="section-head">
          <div>
            <div className="section-title">Allocation</div>
            <div className="section-sub">Click any category to drill into top holdings</div>
          </div>
        </div>
        <AllocationTab />
      </section>

      <section data-tour="holdings">
        <div className="section-head">
          <div>
            <div className="section-title">Holdings by Source</div>
            <div className="section-sub">Click any platform to expand</div>
          </div>
        </div>
        <HoldingsTab onAddSource={() => openModal({ kind: 'addSource' })} />
      </section>
    </div>
  )
}
