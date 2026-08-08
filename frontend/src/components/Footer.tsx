import { LEGAL_NAV } from '../legal/content'
import { SUPPORT_EMAIL, SUPPORT_TELEGRAM, SUPPORT_TELEGRAM_URL } from '../legal/contact'

type Props = {
  /** Compact layout for the narrow login phone frame. */
  compact?: boolean
  /** Same-tab navigation — used on the legal pages themselves. */
  sameTab?: boolean
  /** 釘在視窗底部（內容只略高於視窗的頁面，避免 footer 落在摺線外）。 */
  sticky?: boolean
}

export default function Footer({ compact = false, sameTab = false, sticky = false }: Props) {
  const target = sameTab ? undefined : '_blank'
  const rel = sameTab ? undefined : 'noopener noreferrer'
  const cls = [
    'site-footer',
    compact ? 'site-footer-compact' : '',
    sticky ? 'site-footer-sticky' : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <footer className={cls}>
      <div className="site-footer-inner">
        <div className="site-footer-brand">© 2026 ALL IN · Portfolio tracker</div>
        <nav className="site-footer-links">
          {LEGAL_NAV.map(item => (
            <a key={item.slug} href={item.path} target={target} rel={rel}>
              {item.label}
            </a>
          ))}
        </nav>
        <div className="site-footer-links site-footer-contact">
          <span className="site-footer-label">聯絡我們</span>
          <a href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a>
          <a href={SUPPORT_TELEGRAM_URL} target="_blank" rel="noopener noreferrer">
            Telegram @{SUPPORT_TELEGRAM}
          </a>
        </div>
      </div>
    </footer>
  )
}
