import type { ModalState } from '../../App'

interface Props {
  modal: ModalState | null
  setModal: (m: ModalState | null) => void
}

/**
 * Slice 3 will populate this with AddSourceModal / ConnectSourceModal.
 * For now, just provide the backdrop infrastructure.
 */
export default function ModalHost({ modal, setModal }: Props) {
  if (!modal) return null
  const close = () => setModal(null)
  return (
    <div
      className="modal-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget) close()
      }}
    >
      <div className="modal" style={{ padding: 20 }}>
        <div className="modal-head">
          <div>
            <div className="modal-title">{modal.kind}</div>
            <div className="modal-sub">Coming in Slice 3</div>
          </div>
          <button className="modal-close" onClick={close}>×</button>
        </div>
      </div>
    </div>
  )
}
