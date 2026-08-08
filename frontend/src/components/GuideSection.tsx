import { useState } from 'react'
import { Icon } from './Icon'
import GuideContent from './GuideContent'

function GuideModal({ close }: { close: () => void }) {
  return (
    <div
      className="modal-backdrop"
      onClick={e => {
        if (e.target === e.currentTarget) close()
      }}
    >
      <div className="modal huge">
        <div className="modal-head">
          <div>
            <div className="modal-title">使用說明</div>
            <div className="modal-sub">從連接第一個來源到看懂各項圖表 · 點擊圖片可放大</div>
          </div>
          <button className="modal-close" onClick={close} aria-label="關閉">
            <Icon name="x" />
          </button>
        </div>
        <div className="modal-body guide-doc">
          <GuideContent />
        </div>
      </div>
    </div>
  )
}

export default function GuideSection() {
  const [open, setOpen] = useState(false)

  return (
    <>
      <h3 style={{ marginTop: 24 }}>Guide</h3>
      <p className="muted">不確定怎麼開始？這份圖文說明帶你走過完整流程。</p>
      <div className="card card-pad" data-tour="guide">
        <div className="guide-entry">
          <div>
            <div className="guide-entry-title">使用說明</div>
            <div className="guide-entry-sub">
              六個步驟 · 16 張圖：連接來源、看懂 Dashboard 各項圖表、日常操作
            </div>
          </div>
          <button className="btn btn-outline btn-sm" onClick={() => setOpen(true)}>
            <Icon name="info" /> 開啟說明
          </button>
        </div>
      </div>

      {open && <GuideModal close={() => setOpen(false)} />}
    </>
  )
}
