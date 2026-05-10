import { useEffect, useState } from 'react'
import { Icon } from '../Icon'
import type { SourceTemplate } from '../../data/sourceTemplates'

interface Props {
  credentials: Record<string, unknown>
  setCredential: (key: string, value: unknown) => void
  template: SourceTemplate
}

const PLACEHOLDER_BY_PLATFORM: Record<string, string> = {
  sol_wallet: 'So1...111\n7XyZ...',
  sui_wallet: '0xabc...\n0xdef...',
}

export default function AddressForm({ credentials, setCredential, template }: Props) {
  const placeholder = PLACEHOLDER_BY_PLATFORM[template.id] ?? '0x1234...\n0xabcd...'

  const [addressesText, setAddressesText] = useState<string>(() =>
    Array.isArray(credentials.addresses) ? (credentials.addresses as string[]).join('\n') : '',
  )

  useEffect(() => {
    const list = addressesText.split('\n').map(s => s.trim()).filter(Boolean)
    setCredential('addresses', list)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [addressesText])

  return (
    <>
      <div className="field">
        <label className="field-label">Public address(es)</label>
        <textarea
          className="textarea"
          placeholder={placeholder}
          rows={4}
          value={addressesText}
          onChange={e => setAddressesText(e.target.value)}
        />
        <div className="field-hint">
          One per line. We only read public chain data — never any private keys.
        </div>
      </div>

      <div
        style={{
          background: 'var(--surf)',
          border: '1px solid var(--bdr)',
          padding: 12,
          borderRadius: 8,
          fontSize: 11,
          color: 'var(--fg-2)',
          lineHeight: 1.5,
        }}
      >
        <div
          style={{
            fontWeight: 600,
            color: 'var(--fg)',
            marginBottom: 4,
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}
        >
          <Icon name="info" /> Read-only access
        </div>
        We only query public on-chain balances. Wallet addresses are public — never share private
        keys or seed phrases with anyone.
      </div>
    </>
  )
}
