import { useQuery } from '@tanstack/react-query'
import HoldingsTab from '../components/tabs/HoldingsTab'
import AllocationTab from '../components/tabs/AllocationTab'
import TrendTab from '../components/tabs/TrendTab'
import EmptyState from '../components/EmptyState'
import { listConnectors } from '../api/connectors'
import type { ModalState } from '../App'

interface Props {
  openModal: (m: ModalState) => void
}

/**
 * V2 Dashboard combines Trend + Allocation + Holdings into a single page.
 * Empty state CTA shows when the user has no connectors yet.
 */
export default function DashboardTab({ openModal }: Props) {
  const { data: connectors, isLoading } = useQuery({
    queryKey: ['connectors'],
    queryFn: listConnectors,
  })

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
      <section>
        <div className="section-head">
          <div>
            <div className="section-title">Performance</div>
            <div className="section-sub">Asset trend across categories</div>
          </div>
        </div>
        <TrendTab />
      </section>

      <section>
        <div className="section-head">
          <div>
            <div className="section-title">Allocation</div>
            <div className="section-sub">Click any category to drill into top holdings</div>
          </div>
        </div>
        <AllocationTab />
      </section>

      <section>
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
