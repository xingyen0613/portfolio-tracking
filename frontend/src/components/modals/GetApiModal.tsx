import { useState } from 'react'
import { Icon } from '../Icon'
import type { GetApiConfig } from '../../data/sourceTemplates'

interface Props {
  platformName: string
  config: GetApiConfig
  onBack: () => void
}

const ITEMS = [
  { key: 'account' as const, label: '已有帳號' },
  { key: 'register' as const, label: '尚未註冊' },
]

export default function GetApiModal({ platformName, config, onBack }: Props) {
  const [hovered, setHovered] = useState<'account' | 'register' | null>(null)

  const urlFor = (key: 'account' | 'register') =>
    key === 'account' ? config.hasAccountUrl : config.noAccountUrl
  const tooltipFor = (key: 'account' | 'register') =>
    key === 'account' ? config.hasAccountTooltip : config.noAccountTooltip

  return (
    <div className="modal">
      <div className="modal-head">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button className="modal-close" onClick={onBack} title="返回">
            <Icon name="chevronL" />
          </button>
          <div className="modal-title">取得 {platformName} API</div>
        </div>
      </div>
      <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {ITEMS.map(({ key, label }) => (
          <div
            key={key}
            style={{
              position: 'relative',
              overflow: 'hidden',
              borderRadius: 10,
              border: `1px solid ${hovered === key ? 'var(--accent-line)' : 'var(--bdr)'}`,
              transition: 'border-color 80ms',
            }}
            onMouseEnter={() => setHovered(key)}
            onMouseLeave={() => setHovered(null)}
          >
            <a
              href={urlFor(key)}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: '16px 18px',
                background: 'var(--surf)',
                textDecoration: 'none',
                color: 'var(--fg)',
              }}
            >
              <span style={{ flex: 1, fontWeight: 600, fontSize: 14 }}>{label}</span>
              <Icon name="info" className="nav-icon" />
              <Icon name="chevronR" className="nav-icon" />
            </a>
            {/* Slide-in overlay from right to left */}
            <div
              style={{
                position: 'absolute',
                inset: 0,
                background: 'var(--bg-elev)',
                transform: hovered === key ? 'translateX(0%)' : 'translateX(100%)',
                transition: 'transform 1s ease-out',
                display: 'flex',
                alignItems: 'center',
                padding: '0 18px',
                fontSize: 12,
                color: 'var(--fg-2)',
                lineHeight: 1.55,
                pointerEvents: 'none',
              }}
            >
              {tooltipFor(key)}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
