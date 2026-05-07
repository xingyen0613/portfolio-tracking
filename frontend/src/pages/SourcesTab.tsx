import type { ModalState } from '../App'
import { Icon } from '../components/Icon'

interface Props {
  openModal: (m: ModalState) => void
}

export default function SourcesTab({ openModal }: Props) {
  return (
    <div>
      <div className="section-head">
        <div>
          <div className="section-title">Connected Sources</div>
          <div className="section-sub">Manage your data sources — Slice 3 will populate this list</div>
        </div>
        <button className="btn btn-primary btn-sm" onClick={() => openModal({ kind: 'addSource' })}>
          <Icon name="plus" /> Add source
        </button>
      </div>
      <div className="card card-pad" style={{ color: 'var(--fg-3)', textAlign: 'center', padding: 48 }}>
        Connectors list coming in Slice 3
      </div>
    </div>
  )
}
