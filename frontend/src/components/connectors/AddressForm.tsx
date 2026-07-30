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
        <label className="field-label">公開錢包地址</label>
        <textarea
          className="textarea"
          placeholder={placeholder}
          rows={4}
          value={addressesText}
          onChange={e => setAddressesText(e.target.value)}
        />
        <div className="field-hint">
          每行一個地址。我們只讀取鏈上公開資料，絕不會取得任何私鑰。
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
          <Icon name="info" /> 唯讀存取
        </div>
        我們只查詢鏈上公開餘額。錢包地址本身是公開資訊，但請絕不與任何人分享私鑰或助記詞。
      </div>
    </>
  )
}
