import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Icon } from '../components/Icon'
import {
  type Connector,
  deleteConnector,
  listConnectors,
  refreshConnector,
} from '../api/connectors'
import { getTemplate, type SourceTemplate } from '../data/sourceTemplates'
import type { ModalState } from '../App'

interface Props {
  openModal: (m: ModalState) => void
}

function statusOf(c: Connector): { label: string; cls: string } {
  if (c.last_error) return { label: 'Error', cls: 'status-error' }
  if (c.last_sync_at) return { label: 'Synced', cls: 'status-synced' }
  return { label: 'Pending', cls: 'status-pending' }
}

function formatRelative(iso: string | null): string {
  if (!iso) return 'Never'
  const t = new Date(iso).getTime()
  const diff = Date.now() - t
  if (Number.isNaN(diff)) return iso
  const min = Math.floor(diff / 60000)
  if (min < 1) return 'Just now'
  if (min < 60) return `${min}m ago`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr}h ago`
  const day = Math.floor(hr / 24)
  return `${day}d ago`
}

const WALLET_PLATFORMS = new Set(['evm_wallet', 'sol_wallet', 'sui_wallet'])

function ConnectorRow({
  c,
  template,
  onRefresh,
  onRemove,
  onImport,
  busy,
}: {
  c: Connector
  template: SourceTemplate | undefined
  onRefresh: () => void
  onRemove: () => void
  onImport: () => void
  busy: boolean
}) {
  const status = statusOf(c)
  const abbr = template?.abbr ?? c.platform_name.slice(0, 3).toUpperCase()
  const name = template?.name ?? c.platform_name
  const color = template?.color ?? '#3a3a44'
  const textColor = template?.textColor ?? '#fff'
  const typeLabel = template?.auth === 'apikey'
    ? 'Exchange'
    : template?.auth === 'address'
      ? 'Wallet'
      : template?.auth === 'ibkr'
        ? 'Broker'
        : 'Source'

  return (
    <div className="row-item">
      <div
        className="platform-abbr"
        style={{ background: color, color: textColor }}
      >
        {abbr}
      </div>
      <div className="row-main">
        <div className="row-name">
          {name}
          {c.account_label && (
            <span style={{ color: 'var(--fg-3)', fontWeight: 400, marginLeft: 8 }}>
              · {c.account_label}
            </span>
          )}
        </div>
        <div className="row-meta">
          <span>{typeLabel}</span>
          <span>·</span>
          <span>Last sync {formatRelative(c.last_sync_at)}</span>
          {c.last_error && (
            <>
              <span>·</span>
              <span style={{ color: 'var(--c-neg)' }}>
                {c.last_error.slice(0, 60)}
                {c.last_error.length > 60 ? '…' : ''}
              </span>
            </>
          )}
        </div>
      </div>
      <span className={`platform-status ${status.cls}`}>{status.label}</span>
      <div className="row-actions">
        {!WALLET_PLATFORMS.has(c.platform_name) && (
          <button
            className="icon-btn"
            title="Import history"
            onClick={onImport}
            disabled={busy}
          >
            <Icon name="upload" />
          </button>
        )}
        <button
          className="icon-btn"
          title="Refresh"
          onClick={onRefresh}
          disabled={busy}
        >
          <Icon name="refresh" />
        </button>
        <button
          className="icon-btn"
          title="Remove"
          onClick={onRemove}
          disabled={busy}
        >
          <Icon name="trash" />
        </button>
      </div>
    </div>
  )
}

export default function SourcesTab({ openModal }: Props) {
  const qc = useQueryClient()

  const { data: connectors, isLoading, error } = useQuery({
    queryKey: ['connectors'],
    queryFn: listConnectors,
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteConnector(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['connectors'] }),
  })

  const refreshMut = useMutation({
    mutationFn: (id: string) => refreshConnector(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['connectors'] }),
  })

  const handleRemove = (c: Connector) => {
    const label = c.account_label || c.platform_name
    if (
      !confirm(
        `Remove "${label}"?\n\nThis will also delete all historical data ` +
          `(holdings, snapshots, source runs) belonging to this connector.\n` +
          `Other connectors and your account-level history are not affected.\n\n` +
          `This action cannot be undone.`,
      )
    )
      return
    deleteMut.mutate(c.id)
  }

  return (
    <div>
      <div className="section-head">
        <div>
          <div className="section-title">Connected Sources</div>
          <div className="section-sub">
            {connectors ? `${connectors.length} sources` : 'Loading...'}
            {' · '}sync history and credentials
          </div>
        </div>
        <button
          className="btn btn-primary btn-sm"
          onClick={() => openModal({ kind: 'addSource' })}
        >
          <Icon name="plus" /> Add source
        </button>
      </div>

      {error && (
        <div className="card card-pad" style={{ color: 'var(--c-neg)' }}>
          Failed to load connectors: {(error as Error).message}
        </div>
      )}

      {isLoading && (
        <div className="card card-pad" style={{ color: 'var(--fg-3)', textAlign: 'center', padding: 48 }}>
          Loading…
        </div>
      )}

      {connectors && connectors.length === 0 && (
        <div className="card card-pad" style={{ color: 'var(--fg-3)', textAlign: 'center', padding: 48 }}>
          No sources connected yet. Click <strong>Add source</strong> above to get started.
        </div>
      )}

      {connectors && connectors.length > 0 && (
        <div className="row-list">
          {connectors.map(c => (
            <ConnectorRow
              key={c.id}
              c={c}
              template={getTemplate(c.platform_name)}
              onRefresh={() => refreshMut.mutate(c.id)}
              onRemove={() => handleRemove(c)}
              onImport={() => openModal({ kind: 'importHistory', connector: c })}
              busy={
                (deleteMut.isPending && deleteMut.variables === c.id) ||
                (refreshMut.isPending && refreshMut.variables === c.id)
              }
            />
          ))}
        </div>
      )}
    </div>
  )
}
