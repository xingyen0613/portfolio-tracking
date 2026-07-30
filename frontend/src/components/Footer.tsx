import { LEGAL_NAV } from '../legal/content'
import { SUPPORT_EMAIL, SUPPORT_TELEGRAM, SUPPORT_TELEGRAM_URL } from '../legal/contact'

type Props = {
  /** Compact layout for the narrow login phone frame. */
  compact?: boolean
  /** Same-tab navigation — used on the legal pages themselves. */
  sameTab?: boolean
}

export default function Footer({ compact = false, sameTab = false }: Props) {
  const target = sameTab ? undefined : '_blank'
  const rel = sameTab ? undefined : 'noopener noreferrer'

  return (
    <footer className={compact ? 'site-footer site-footer-compact' : 'site-footer'}>
      <div className="site-footer-inner">
        <div className="site-footer-brand">© 2026 ALL IN · Portfolio tracker</div>
        <nav className="site-footer-links">
          {LEGAL_NAV.map(item => (
            <a key={item.slug} href={item.path} target={target} rel={rel}>
              {item.label}
            </a>
          ))}
        </nav>
        <div className="site-footer-links">
          <a href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a>
          <a href={SUPPORT_TELEGRAM_URL} target="_blank" rel="noopener noreferrer">
            @{SUPPORT_TELEGRAM}
          </a>
        </div>
      </div>
    </footer>
  )
}
