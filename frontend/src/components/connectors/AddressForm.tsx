import { Icon } from '../Icon'
import type { SourceTemplate } from '../../data/sourceTemplates'

interface Props {
  credentials: Record<string, unknown>
  setCredential: (key: string, value: unknown) => void
  template: SourceTemplate
}

const EVM_CHAINS = [
  { id: 'ethereum', label: 'Ethereum' },
  { id: 'polygon',  label: 'Polygon' },
  { id: 'arbitrum', label: 'Arbitrum' },
  { id: 'optimism', label: 'Optimism' },
  { id: 'base',     label: 'Base' },
  { id: 'bsc',      label: 'BSC' },
  { id: 'avalanche', label: 'Avalanche' },
  { id: 'linea',    label: 'Linea' },
  { id: 'stable',   label: 'Stable' },
]

const DEFAULT_EVM_CHAINS = ['ethereum', 'polygon', 'arbitrum']

export default function AddressForm({ credentials, setCredential, template }: Props) {
  const isSolana = template.id === 'sol_wallet'

  const addressesText =
    Array.isArray(credentials.addresses)
      ? (credentials.addresses as string[]).join('\n')
      : ''

  const selectedChains: string[] = Array.isArray(credentials.chains)
    ? (credentials.chains as string[])
    : DEFAULT_EVM_CHAINS

  // Initialise default chains for EVM the first time
  if (!isSolana && credentials.chains === undefined) {
    setCredential('chains', DEFAULT_EVM_CHAINS)
  }

  const setAddresses = (text: string) => {
    const list = text.split('\n').map(s => s.trim()).filter(Boolean)
    setCredential('addresses', list)
  }

  const toggleChain = (chain: string) => {
    const next = selectedChains.includes(chain)
      ? selectedChains.filter(c => c !== chain)
      : [...selectedChains, chain]
    setCredential('chains', next)
  }

  return (
    <>
      <div className="field">
        <label className="field-label">Alchemy API Key</label>
        <input
          className="input mono"
          placeholder="Paste your Alchemy API key"
          value={(credentials.api_key as string) ?? ''}
          onChange={e => setCredential('api_key', e.target.value)}
        />
        <div className="field-hint">
          Get one at <span className="mono">dashboard.alchemy.com</span>. We only call read-only RPC.
        </div>
      </div>

      <div className="field">
        <label className="field-label">Public address(es)</label>
        <textarea
          className="textarea"
          placeholder={isSolana ? 'So1...111\n7XyZ...' : '0x1234...\n0xabcd...'}
          rows={4}
          value={addressesText}
          onChange={e => setAddresses(e.target.value)}
        />
        <div className="field-hint">
          One per line. We only read public chain data — never any private keys.
        </div>
      </div>

      {!isSolana && (
        <div className="field">
          <label className="field-label">Networks</label>
          <div className="chip-row">
            {EVM_CHAINS.map(c => {
              const active = selectedChains.includes(c.id)
              return (
                <button
                  key={c.id}
                  type="button"
                  className={`chip ${active ? 'active' : ''}`}
                  onClick={() => toggleChain(c.id)}
                  style={{
                    color: active ? 'var(--accent)' : 'var(--fg-2)',
                    borderColor: active ? 'var(--accent-line)' : 'var(--bdr)',
                  }}
                >
                  {active && '✓ '}
                  {c.label}
                </button>
              )
            })}
          </div>
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
          <Icon name="info" /> Read-only access
        </div>
        We only query public on-chain balances via your Alchemy key. Wallet addresses are public — never
        share private keys or seed phrases with anyone.
      </div>
    </>
  )
}
