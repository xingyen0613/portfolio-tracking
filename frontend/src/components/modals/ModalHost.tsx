import type { ModalState } from '../../App'
import AddSourceModal from './AddSourceModal'
import ConnectSourceModal from './ConnectSourceModal'

interface Props {
  modal: ModalState | null
  setModal: (m: ModalState | null) => void
}

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
      {modal.kind === 'addSource' && <AddSourceModal close={close} setModal={setModal} />}
      {modal.kind === 'connect' && (
        <ConnectSourceModal templateId={modal.templateId} close={close} setModal={setModal} />
      )}
      {modal.kind === 'editSource' && (
        <div className="modal" style={{ padding: 20 }}>
          <div className="modal-head">
            <div className="modal-title">Edit source</div>
            <button className="modal-close" onClick={close}>×</button>
          </div>
          <div className="modal-body" style={{ color: 'var(--fg-3)' }}>
            Coming soon.
          </div>
        </div>
      )}
    </div>
  )
}
