import { useState } from 'react'
import { Icon } from '../Icon'
import {
  CATEGORY_LABEL,
  SOURCE_TEMPLATES,
  type Category,
  type SourceTemplate,
} from '../../data/sourceTemplates'
import type { ModalState } from '../../App'

interface Props {
  close: () => void
  setModal: (m: ModalState | null) => void
}

const CATEGORIES: ('all' | Category)[] = ['all', 'crypto', 'us', 'tw', 'other']

export default function AddSourceModal({ close, setModal }: Props) {
  const [cat, setCat] = useState<'all' | Category>('all')
  const filtered = SOURCE_TEMPLATES.filter(t => cat === 'all' || t.category === cat)

  const handlePick = (t: SourceTemplate) => {
    setModal({ kind: 'connect', templateId: t.id })
  }

  return (
    <div className="modal wide">
      <div className="modal-head">
        <div>
          <div className="modal-title">Add a data source</div>
          <div className="modal-sub">Connect an exchange, wallet, broker, or manual source</div>
        </div>
        <button className="modal-close" onClick={close}>
          <Icon name="x" />
        </button>
      </div>
      <div className="modal-body">
        <div className="src-cat-row">
          {CATEGORIES.map(c => (
            <button
              key={c}
              className={`chip ${cat === c ? 'active' : ''}`}
              onClick={() => setCat(c)}
              style={{
                borderColor: cat === c ? 'var(--accent-line)' : 'var(--bdr)',
                color: cat === c ? 'var(--accent)' : 'var(--fg-2)',
              }}
            >
              {CATEGORY_LABEL[c]}
            </button>
          ))}
        </div>
        <div className="src-grid">
          {filtered.map(t => (
            <button
              key={t.id}
              className="src-card"
              onClick={() => handlePick(t)}
              style={{ opacity: t.implemented ? 1 : 0.7 }}
            >
              <div
                className="platform-abbr"
                style={{ background: t.color, color: t.textColor }}
              >
                {t.abbr}
              </div>
              <div style={{ flex: 1, textAlign: 'left' }}>
                <div className="src-name">{t.name}</div>
                <div className="src-desc">
                  {t.implemented ? t.desc : (t.comingSoon ?? 'Coming soon')}
                </div>
              </div>
              <Icon name="chevronR" />
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
