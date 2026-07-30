import { Icon } from '../Icon'
import MaskedInput from '../MaskedInput'
import type { SourceTemplate } from '../../data/sourceTemplates'

interface Props {
  credentials: Record<string, unknown>
  setCredential: (key: string, value: unknown) => void
  template: SourceTemplate
}

export default function ApiKeyForm({ credentials, setCredential, template }: Props) {
  const showPassphrase = template.id === 'okx' || template.id === 'coinbase'
  return (
    <>
      <div className="field">
        <label className="field-label">API Key</label>
        <MaskedInput
          className="input mono"
          placeholder="貼上唯讀 API Key"
          value={(credentials.api_key as string) ?? ''}
          onChange={v => setCredential('api_key', v)}
        />
      </div>
      <div className="field">
        <label className="field-label">API Secret</label>
        <MaskedInput
          className="input mono"
          placeholder="••••••••••••••••"
          value={(credentials.secret as string) ?? ''}
          onChange={v => setCredential('secret', v)}
        />
      </div>
      {showPassphrase && (
        <div className="field">
          <label className="field-label">Passphrase</label>
          <MaskedInput
            className="input mono"
            placeholder="••••••••"
            value={(credentials.passphrase as string) ?? ''}
            onChange={v => setCredential('passphrase', v)}
          />
        </div>
      )}
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
          <Icon name="info" /> 僅開啟唯讀權限
        </div>
        建立 API Key 時只勾選 <span className="kbd">Read</span>（唯讀）權限，切勿開啟交易或提款權限。
      </div>
    </>
  )
}
