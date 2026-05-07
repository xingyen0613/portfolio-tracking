import { Icon } from '../Icon'
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
        <input
          className="input mono"
          placeholder="Paste read-only API key"
          value={(credentials.api_key as string) ?? ''}
          onChange={e => setCredential('api_key', e.target.value)}
        />
      </div>
      <div className="field">
        <label className="field-label">API Secret</label>
        <input
          className="input mono"
          type="password"
          placeholder="••••••••••••••••"
          value={(credentials.secret as string) ?? ''}
          onChange={e => setCredential('secret', e.target.value)}
        />
      </div>
      {showPassphrase && (
        <div className="field">
          <label className="field-label">Passphrase</label>
          <input
            className="input mono"
            type="password"
            placeholder="••••••••"
            value={(credentials.passphrase as string) ?? ''}
            onChange={e => setCredential('passphrase', e.target.value)}
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
          <Icon name="info" /> Read-only permissions only
        </div>
        Create the API key with <span className="kbd">Read</span> permission only. Never enable trading or
        withdrawal.
      </div>
    </>
  )
}
