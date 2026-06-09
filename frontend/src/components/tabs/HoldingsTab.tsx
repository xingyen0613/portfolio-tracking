import { Fragment, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'
import { listConnectors, type Connector } from '../../api/connectors'
import { useCurrency } from '../../context/CurrencyContext'
import { getTemplate } from '../../data/sourceTemplates'

// ── Types ─────────────────────────────────────────────────────────────────────

interface HoldingRow  { symbol: string; name: string; quantity: string; price: string; value_usd: number }
interface Section     { label: string; total_usd: number; rows: HoldingRow[] }
interface Account     { account_key: string; address: string | null; chain: string | null; label: string; total_usd: number; sections: Section[] }
interface Platform    { name: string; display: string; abbr: string; color: string; fg: string; category: string; total_usd: number; sections: Section[]; accounts?: Account[]; chain?: string | null }
interface Summary     { total_usd: number; crypto_usd?: number; us_stock_usd?: number; tw_stock_usd?: number }
interface HoldingsData{ summary: Summary; platforms: Platform[] }

// ── Constants ─────────────────────────────────────────────────────────────────


// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtAddr(addr: string): string {
  if (addr.length <= 14) return addr
  return `${addr.slice(0, 6)}…${addr.slice(-4)}`
}

// ── Address badge row (for wallet platforms) ──────────────────────────────────

function AddressBadge({ account, totalUsd }: { account: Account; totalUsd: number }) {
  const { fmt } = useCurrency()
  // Wallet accounts have an on-chain address → render as monospaced address + chain.
  // Non-wallet accounts (multiple connectors on the same exchange) have no
  // address → render the user-given label instead.
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 6, padding: '6px 14px',
      background: 'var(--bg)', borderBottom: '1px solid var(--bdr2)',
    }}>
      {account.address ? (
        <code style={{
          fontSize: 11, fontFamily: 'JetBrains Mono, monospace',
          color: 'var(--fg2)', letterSpacing: '.3px',
        }}>
          {fmtAddr(account.address)}
        </code>
      ) : (
        <span style={{
          fontSize: 12, fontWeight: 500, color: 'var(--fg2)', letterSpacing: '.2px',
        }}>
          {account.label}
        </span>
      )}
      {account.chain && (
        <span style={{
          fontSize: 10, fontWeight: 600, padding: '1px 5px',
          borderRadius: 3, background: 'var(--surf3)', color: 'var(--fg3)',
          textTransform: 'uppercase', letterSpacing: '.4px',
        }}>
          {account.chain}
        </span>
      )}
      <span style={{
        marginLeft: 'auto', fontFamily: 'JetBrains Mono, monospace',
        fontSize: 11, color: 'var(--fg3)',
      }}>
        {fmt(totalUsd)}
      </span>
    </div>
  )
}

// ── Chevron icon ──────────────────────────────────────────────────────────────

function Chevron({ open }: { open: boolean }) {
  return (
    <svg width={14} height={14} viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth={1.5}
      style={{ transform: open ? 'rotate(90deg)' : 'none', transition: 'transform 200ms ease', flexShrink: 0, color: 'var(--fg3)' }}>
      <path d="M5 3l4 4-4 4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

// ── Holding row (own hover state, avoids imperative DOM mutation) ─────────────

function HoldingRowView({ row }: { row: HoldingRow }) {
  const [hovered, setHovered] = useState(false)
  const { fmt } = useCurrency()
  const bg = hovered ? 'var(--surf2)' : undefined

  return (
    <tr onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}>
      <td style={{ padding: '8px 14px', fontSize: 12, borderBottom: '1px solid var(--bdr2)', background: bg }}>
        <span style={{
          display: 'inline-block', background: 'var(--surf3)', border: '1px solid var(--bdr)',
          borderRadius: 4, padding: '2px 5px', fontFamily: 'JetBrains Mono, monospace', fontSize: 11, fontWeight: 500,
        }}>
          {row.symbol}
        </span>
      </td>
      {[row.quantity, row.price].map((v, j) => (
        <td key={j} style={{
          padding: '8px 14px', fontSize: 12, textAlign: 'right',
          fontFamily: 'JetBrains Mono, monospace', borderBottom: '1px solid var(--bdr2)',
          color: 'var(--fg2)', background: bg,
        }}>
          {v}
        </td>
      ))}
      <td style={{
        padding: '8px 14px', fontSize: 12, textAlign: 'right',
        fontFamily: 'JetBrains Mono, monospace', borderBottom: '1px solid var(--bdr2)',
        color: row.value_usd < 0 ? 'var(--red)' : 'var(--fg1)', background: bg,
      }}>
        {fmt(row.value_usd)}
      </td>
    </tr>
  )
}

// ── Add source row ────────────────────────────────────────────────────────────

function AddSourceRow({ onClick }: { onClick: () => void }) {
  const [hovered, setHovered] = useState(false)
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'flex', alignItems: 'center', gap: 14, padding: '14px 16px',
        border: '1.5px dashed var(--bdr)', borderRadius: 8, cursor: 'pointer',
        background: hovered ? 'var(--surf2)' : 'transparent',
        transition: 'background 120ms',
      }}
    >
      <div style={{
        width: 28, height: 28, borderRadius: 6, border: '1.5px dashed var(--bdr)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        flexShrink: 0, color: 'var(--fg3)',
      }}>
        <svg width={14} height={14} viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round">
          <path d="M7 2v10M2 7h10" />
        </svg>
      </div>
      <div>
        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--fg1)' }}>Add another source</div>
        <div style={{ fontSize: 11, color: 'var(--fg3)', marginTop: 2 }}>Connect an exchange, wallet, broker, or add manual assets</div>
      </div>
    </div>
  )
}

// ── Platform card ─────────────────────────────────────────────────────────────

interface PlatformStatus {
  label: string
  cls: string
  errorMessage?: string
}

function platformStatus(connectors: Connector[]): PlatformStatus | null {
  if (connectors.length === 0) return null
  const errored = connectors.find(c => c.last_error)
  if (errored) {
    return { label: 'Error', cls: 'status-error', errorMessage: errored.last_error ?? undefined }
  }
  const synced = connectors.find(c => c.last_sync_at)
  if (synced) return { label: 'Synced', cls: 'status-synced' }
  return { label: 'Pending', cls: 'status-pending' }
}

function PlatformCard({
  p,
  connectors,
  onReconnect,
}: {
  p: Platform
  connectors: Connector[]
  onReconnect?: () => void
}) {
  const [open, setOpen]       = useState(false)
  const [hovered, setHovered] = useState(false)
  const status = platformStatus(connectors)
  const { fmt } = useCurrency()

  return (
    <div style={{ background: 'var(--surf)', border: '1px solid var(--bdr)', borderRadius: 8, overflow: 'hidden' }}>

      {/* Header */}
      <div
        onClick={() => setOpen(o => !o)}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        style={{
          display: 'flex', alignItems: 'center', gap: 10, padding: '11px 14px', cursor: 'pointer',
          borderBottom: open ? '1px solid var(--bdr2)' : 'none',
          background: hovered ? 'var(--surf2)' : 'transparent',
          transition: 'background 120ms',
        }}
      >
        {getTemplate(p.name)?.logoUrl ? (
          <img
            src={getTemplate(p.name)!.logoUrl}
            alt={p.display}
            style={{ width: 26, height: 26, borderRadius: 5, flexShrink: 0, objectFit: 'cover' }}
          />
        ) : (
          <div style={{
            width: 26, height: 26, borderRadius: 5, display: 'flex', alignItems: 'center',
            justifyContent: 'center', fontSize: 10, fontWeight: 700, flexShrink: 0,
            background: p.color, color: p.fg,
          }}>
            {p.abbr}
          </div>
        )}
        <div style={{ fontSize: 13, fontWeight: 600 }}>{p.display}</div>
        <div style={{ flex: 1 }} />
        {status && (
          <span className={`platform-status ${status.cls}`} style={{ marginRight: 4 }}>
            {status.label}
          </span>
        )}
        <div style={{
          fontFamily: 'JetBrains Mono, monospace', fontSize: 13,
          color: p.total_usd < 0 ? 'var(--red)' : 'var(--fg1)',
        }}>
          {fmt(p.total_usd)}
        </div>
        <Chevron open={open} />
      </div>

      {/* Inline error banner with Reconnect CTA */}
      {status?.errorMessage && open && (
        <div
          style={{
            padding: '10px 14px',
            background: 'rgba(236,91,126,0.08)',
            borderBottom: '1px solid var(--bdr2)',
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            fontSize: 12,
          }}
        >
          <div style={{ flex: 1, color: 'var(--c-neg)' }}>
            <strong>Sync failed:</strong> {status.errorMessage.slice(0, 120)}
            {status.errorMessage.length > 120 ? '…' : ''}
          </div>
          {onReconnect && (
            <button className="btn btn-outline btn-sm" onClick={onReconnect}>
              Reconnect
            </button>
          )}
        </div>
      )}

      {/* Collapsible content — maxHeight transition avoids layout jump */}
      <div style={{
        maxHeight: open ? '4000px' : '0',
        overflow: 'hidden',
        transition: open ? 'max-height 500ms ease' : 'max-height 200ms ease',
      }}>
        {p.accounts && p.accounts.length > 0 ? (
          // Wallet platform: group by address/chain
          p.accounts.map(acct => (
            <div key={acct.account_key}>
              <AddressBadge account={acct} totalUsd={acct.total_usd} />
              {acct.sections.length > 0 && (
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr>
                      {['代碼', '數量', '單價', '市值'].map((h, i) => (
                        <th key={h} style={{
                          padding: '7px 14px', fontSize: 10, color: 'var(--fg3)', fontWeight: 500,
                          textAlign: i === 0 ? 'left' : 'right',
                          borderBottom: '1px solid var(--bdr2)', letterSpacing: '.4px',
                        }}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {acct.sections.map(sec => (
                      <Fragment key={sec.label}>
                        <tr>
                          <td colSpan={4} style={{ padding: 0 }}>
                            <div style={{
                              padding: '5px 14px', fontSize: 10, fontWeight: 600, color: 'var(--fg3)',
                              background: 'var(--surf2)', textTransform: 'uppercase', letterSpacing: '.5px',
                              display: 'flex', alignItems: 'center', gap: 8,
                            }}>
                              {sec.label}
                              <span style={{ marginLeft: 'auto', fontFamily: 'JetBrains Mono, monospace', color: 'var(--fg2)' }}>
                                {fmt(sec.total_usd)}
                              </span>
                            </div>
                          </td>
                        </tr>
                        {sec.rows.map((row, i) => <HoldingRowView key={i} row={row} />)}
                      </Fragment>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          ))
        ) : (
          // Regular platform: flat sections
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                {['代碼', '數量', '單價', '市值'].map((h, i) => (
                  <th key={h} style={{
                    padding: '7px 14px', fontSize: 10, color: 'var(--fg3)', fontWeight: 500,
                    textAlign: i === 0 ? 'left' : 'right',
                    borderBottom: '1px solid var(--bdr2)', letterSpacing: '.4px',
                  }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {p.sections.map(sec => (
                <Fragment key={sec.label}>
                  <tr>
                    <td colSpan={4} style={{ padding: 0 }}>
                      <div style={{
                        padding: '5px 14px', fontSize: 10, fontWeight: 600, color: 'var(--fg3)',
                        background: 'var(--bg)', textTransform: 'uppercase', letterSpacing: '.5px',
                        display: 'flex', alignItems: 'center', gap: 8,
                      }}>
                        {sec.label}
                        <span style={{ marginLeft: 'auto', fontFamily: 'JetBrains Mono, monospace', color: 'var(--fg2)' }}>
                          {fmt(sec.total_usd)}
                        </span>
                      </div>
                    </td>
                  </tr>
                  {sec.rows.map((row, i) => <HoldingRowView key={i} row={row} />)}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>

    </div>
  )
}

// ── Main Component ────────────────────────────────────────────────────────────

interface HoldingsTabProps {
  onAddSource?: () => void
}

export default function HoldingsTab({ onAddSource }: HoldingsTabProps = {}) {
  const { data, isLoading } = useQuery<HoldingsData>({
    queryKey: ['holdings'],
    queryFn: () => api.get('/api/holdings').then(r => r.data),
  })

  const { data: connectors = [] } = useQuery({
    queryKey: ['connectors'],
    queryFn: listConnectors,
  })

  const connectorsByPlatform: Record<string, Connector[]> = {}
  for (const c of connectors) {
    if (!connectorsByPlatform[c.platform_name]) connectorsByPlatform[c.platform_name] = []
    connectorsByPlatform[c.platform_name].push(c)
  }

  if (isLoading) {
    return (
      <div style={{ color: 'var(--fg3)', fontSize: 11, padding: 24, textAlign: 'center', fontFamily: 'JetBrains Mono, monospace' }}>
        載入中...
      </div>
    )
  }

  const platforms = data?.platforms ?? []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {platforms.map(p => (
        <PlatformCard
          key={p.name}
          p={p}
          connectors={connectorsByPlatform[p.name] ?? []}
          onReconnect={onAddSource}
        />
      ))}
      {onAddSource && (
        <AddSourceRow onClick={onAddSource} />
      )}
    </div>
  )
}
