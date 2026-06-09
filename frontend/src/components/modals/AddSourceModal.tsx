import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Icon } from '../Icon'
import {
  CATEGORY_LABEL,
  SOURCE_TEMPLATES,
  type Category,
  type SourceTemplate,
} from '../../data/sourceTemplates'
import { listConnectors } from '../../api/connectors'
import type { ModalState } from '../../App'

interface Props {
  close: () => void
  setModal: (m: ModalState | null) => void
}

const CATEGORIES: ('all' | Category)[] = ['all', 'crypto', 'us', 'tw', 'other']

export default function AddSourceModal({ close, setModal }: Props) {
  const [cat, setCat] = useState<'all' | Category>('all')
  const filtered = SOURCE_TEMPLATES.filter(t => cat === 'all' || t.category === cat)

  const { data: connectors } = useQuery({ queryKey: ['connectors'], queryFn: listConnectors })
  const existingPlatforms = new Set(connectors?.map(c => c.platform_name) ?? [])

  const isDisabled = (t: SourceTemplate) =>
    !t.implemented || (!!t.singleInstance && existingPlatforms.has(t.id))

  const handlePick = (t: SourceTemplate) => {
    if (isDisabled(t)) return
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
          {filtered.map(t => {
            const alreadyConnected = !!t.singleInstance && existingPlatforms.has(t.id)
            const disabled = !t.implemented || alreadyConnected
            return (
              <button
                key={t.id}
                className="src-card"
                onClick={() => handlePick(t)}
                disabled={disabled}
                title={alreadyConnected ? '已連接，每個帳號只能新增一個此來源' : undefined}
                style={{ opacity: disabled ? 0.5 : 1, cursor: disabled ? 'not-allowed' : 'pointer' }}
              >
                {t.logoUrl ? (
                  <img
                    src={t.logoUrl}
                    alt={t.name}
                    className="platform-abbr"
                    style={{ objectFit: 'cover', padding: 0 }}
                  />
                ) : (
                  <div
                    className="platform-abbr"
                    style={{ background: t.color, color: t.textColor }}
                  >
                    {t.abbr}
                  </div>
                )}
                <div style={{ flex: 1, textAlign: 'left' }}>
                  <div className="src-name">{t.name}</div>
                  <div className="src-desc">
                    {alreadyConnected
                      ? '已連接'
                      : t.implemented
                        ? t.desc
                        : (t.comingSoon ?? 'Coming soon')}
                  </div>
                </div>
                <Icon name="chevronR" />
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}
