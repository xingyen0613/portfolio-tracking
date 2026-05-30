import type { ModalState } from '../../App'
import AddSourceModal from './AddSourceModal'
import ConnectSourceModal from './ConnectSourceModal'
import EditSourceModal from './EditSourceModal'
import ImportHistoryModal from './ImportHistoryModal'

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
        <EditSourceModal connectorId={modal.connectorId} close={close} />
      )}
      {modal.kind === 'importHistory' && (
        <ImportHistoryModal connector={modal.connector} close={close} />
      )}
    </div>
  )
}
