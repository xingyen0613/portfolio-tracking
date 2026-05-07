import HoldingsTab from '../components/tabs/HoldingsTab'
import AllocationTab from '../components/tabs/AllocationTab'
import TrendTab from '../components/tabs/TrendTab'
import type { ModalState } from '../App'

interface Props {
  openModal: (m: ModalState) => void
}

/**
 * V2 Dashboard combines Trend + Allocation + Holdings into a single page.
 * The legacy tab components are reused as embedded sections; visual polish to
 * match V2 design comes in Slice 5.
 */
export default function DashboardTab({ openModal: _openModal }: Props) {
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
        <HoldingsTab />
      </section>
    </div>
  )
}
