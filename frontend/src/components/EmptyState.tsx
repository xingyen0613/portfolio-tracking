import { Icon, type IconName } from './Icon'

interface Props {
  icon?: IconName
  title: string
  description?: string
  ctaLabel?: string
  onCta?: () => void
}

export default function EmptyState({
  icon = 'plug',
  title,
  description,
  ctaLabel,
  onCta,
}: Props) {
  return (
    <div
      className="card"
      style={{
        padding: '64px 24px',
        textAlign: 'center',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 16,
      }}
    >
      <div
        className="empty-icon"
        style={{
          width: 56,
          height: 56,
          borderRadius: 14,
          background: 'var(--accent-soft)',
          color: 'var(--accent)',
          display: 'grid',
          placeItems: 'center',
        }}
      >
        <Icon name={icon} className="" />
      </div>
      <div>
        <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 6 }}>{title}</div>
        {description && (
          <div style={{ fontSize: 12, color: 'var(--fg-3)', maxWidth: 420 }}>
            {description}
          </div>
        )}
      </div>
      {ctaLabel && onCta && (
        <button className="btn btn-primary" onClick={onCta} style={{ marginTop: 4 }}>
          <Icon name="plus" />
          {ctaLabel}
        </button>
      )}
    </div>
  )
}
