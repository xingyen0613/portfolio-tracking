import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Icon } from '../components/Icon'
import {
  type Connector,
  deleteConnector,
  getConnectorCredentials,
  initiateYuantaOAuth,
  listConnectors,
  refreshConnector,
} from '../api/connectors'
import { getTemplate, type SourceTemplate } from '../data/sourceTemplates'
import { useDemo } from '../context/DemoContext'
import { DEMO_CONNECTORS } from '../data/demoData'
import type { ModalState } from '../App'

function DemoLock({ children }: { children: React.ReactNode }) {
  const [flash, setFlash] = useState(false)
  return (
    <div
      style={{ position: 'relative', display: 'inline-flex' }}
      onClick={e => {
        e.stopPropagation()
        setFlash(true)
        setTimeout(() => setFlash(false), 1400)
      }}
      title="展示模式，無法操作"
    >
      <div style={{ opacity: 0.4, pointerEvents: 'none' }}>{children}</div>
      {flash && (
        <div style={{
          position: 'absolute', bottom: '110%', left: '50%', transform: 'translateX(-50%)',
          background: 'var(--surf-3)', border: '1px solid var(--bdr)',
          borderRadius: 5, padding: '3px 8px', fontSize: 10, color: 'var(--fg-2)',
          whiteSpace: 'nowrap', zIndex: 999, pointerEvents: 'none',
          animation: 'demoFlash 1.4s ease forwards',
        }}>
          展示模式
        </div>
      )}
    </div>
  )
}

interface Props {
  openModal: (m: ModalState) => void
  yuantaFetchingUntil?: number | null
}

function statusOf(c: Connector): { label: string; cls: string } {
  if (c.last_error) return { label: '錯誤', cls: 'status-error' }
  if (c.last_sync_at) return { label: '已同步', cls: 'status-synced' }
  return { label: '待處理', cls: 'status-pending' }
}

function formatRelative(iso: string | null): string {
  if (!iso) return '從未'
  const t = new Date(iso).getTime()
  const diff = Date.now() - t
  if (Number.isNaN(diff)) return iso
  const min = Math.floor(diff / 60000)
  if (min < 1) return '剛剛'
  if (min < 60) return `${min} 分鐘前`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr} 小時前`
  const day = Math.floor(hr / 24)
  return `${day} 天前`
}

const WALLET_PLATFORMS = new Set(['evm_wallet', 'sol_wallet', 'sui_wallet'])
// 手動 CSV 來源沒有可同步的外部帳戶，後端也會擋 refresh
const NO_REFRESH_PLATFORMS = new Set(['manual'])

function ConnectorRow({
  c,
  template,
  onRefresh,
  onRemove,
  onImport,
  onEdit,
  onReauthorize,
  busy,
  deleting,
  reauthorizing,
  isDemo,
}: {
  c: Connector
  template: SourceTemplate | undefined
  onRefresh: () => void
  onRemove: () => void
  onImport: () => void
  onEdit: () => void
  onReauthorize?: () => void
  busy: boolean
  deleting: boolean
  reauthorizing?: boolean
  isDemo?: boolean
}) {
  const status = deleting
    ? { label: '移除中', cls: 'status-fetching' }
    : busy
      ? { label: '抓取中', cls: 'status-fetching' }
      : statusOf(c)
  const abbr = template?.abbr ?? c.platform_name.slice(0, 3).toUpperCase()
  const name = template?.name ?? c.platform_name
  const color = template?.color ?? '#3a3a44'
  const textColor = template?.textColor ?? '#fff'
  const typeLabel = template?.auth === 'apikey'
    ? '交易所'
    : template?.auth === 'address'
      ? '錢包'
      : template?.auth === 'ibkr'
        ? '券商'
        : '來源'

  return (
    <div className="row-item">
      {template?.logoUrl ? (
        <img
          src={template.logoUrl}
          alt={name}
          className="platform-abbr"
          style={{ objectFit: 'cover', padding: 0 }}
        />
      ) : (
        <div
          className="platform-abbr"
          style={{ background: color, color: textColor }}
        >
          {abbr}
        </div>
      )}
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
          <span>最後同步 {formatRelative(c.last_sync_at)}</span>
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
        {isDemo ? (
          <>
            {!WALLET_PLATFORMS.has(c.platform_name) && (
              <DemoLock><button className="icon-btn"><Icon name="upload" /></button></DemoLock>
            )}
            <DemoLock><button className="icon-btn"><Icon name="edit" /></button></DemoLock>
            <DemoLock><button className="icon-btn"><Icon name="refresh" /></button></DemoLock>
            <DemoLock><button className="icon-btn"><Icon name="trash" /></button></DemoLock>
          </>
        ) : (
          <>
            {!WALLET_PLATFORMS.has(c.platform_name) && (
              <button
                className="icon-btn"
                title="匯入歷史紀錄"
                onClick={onImport}
                disabled={busy || deleting}
              >
                <Icon name="upload" />
              </button>
            )}
            {onReauthorize && (
              <button
                className={`icon-btn${reauthorizing ? ' btn-spinning' : ''}`}
                title="重新授權 Gmail"
                onClick={onReauthorize}
                disabled={busy || deleting || reauthorizing}
              >
                <Icon name="key" />
              </button>
            )}
            <button
              className="icon-btn"
              title="編輯"
              onClick={onEdit}
              disabled={busy || deleting}
            >
              <Icon name="edit" />
            </button>
            {!NO_REFRESH_PLATFORMS.has(c.platform_name) && (
              <button
                className={`icon-btn${busy ? ' btn-spinning' : ''}`}
                title="重新整理"
                onClick={onRefresh}
                disabled={busy || deleting}
              >
                <Icon name="refresh" />
              </button>
            )}
            <button
              className="icon-btn"
              title="移除"
              onClick={onRemove}
              disabled={busy || deleting}
            >
              <Icon name="trash" />
            </button>
          </>
        )}
      </div>
    </div>
  )
}

export default function SourcesTab({ openModal, yuantaFetchingUntil }: Props) {
  const qc = useQueryClient()
  const { isDemo } = useDemo()
  const [reauthorizingId, setReauthorizingId] = useState<string | null>(null)
  const isYuantaFetching = !!yuantaFetchingUntil && Date.now() < yuantaFetchingUntil

  const handleReauthorize = async (c: Connector) => {
    setReauthorizingId(c.id)
    try {
      const creds = await getConnectorCredentials(c.id)
      const pdfPassword = (creds.pdf_password as string) ?? ''
      const gmailAddress = (creds.gmail_address as string) || undefined
      const { authorize_url } = await initiateYuantaOAuth(pdfPassword, gmailAddress)
      window.location.href = authorize_url
    } catch {
      alert('無法取得授權連結，請稍後再試。')
      setReauthorizingId(null)
    }
  }

  const { data: connectors, isLoading, error } = useQuery({
    queryKey: ['connectors'],
    queryFn: listConnectors,
    enabled: !isDemo,
    initialData: isDemo ? DEMO_CONNECTORS : undefined,
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteConnector(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['connectors'] }),
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : '未知錯誤'
      alert(`刪除連接器失敗：${msg}`)
    },
  })

  const refreshMut = useMutation({
    mutationFn: (id: string) => refreshConnector(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['connectors'] })
      qc.invalidateQueries({ queryKey: ['holdings'] })
      qc.invalidateQueries({ queryKey: ['portfolio/history'] })
      qc.invalidateQueries({ queryKey: ['portfolio/allocation'] })
    },
  })

  const handleRemove = (c: Connector) => {
    const label = c.account_label || c.platform_name
    if (
      !confirm(
        `確定要移除「${label}」？\n\n這將同時刪除此連接器所屬的所有歷史資料` +
          `（持倉、快照、來源紀錄）。\n` +
          `其他連接器與帳戶層級的歷史紀錄不受影響。\n\n` +
          `此操作無法復原。`,
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
            {connectors ? `${connectors.length} 個來源` : '載入中...'}
            {' · '}同步紀錄與憑證
          </div>
        </div>
        <button
          className="btn btn-primary btn-sm"
          onClick={() => openModal({ kind: 'addSource' })}
        >
          <Icon name="plus" /> 新增來源
        </button>
      </div>

      {error && (
        <div className="card card-pad" style={{ color: 'var(--c-neg)' }}>
          載入連接器失敗：{(error as Error).message}
        </div>
      )}

      {isLoading && (
        <div className="card card-pad" style={{ color: 'var(--fg-3)', textAlign: 'center', padding: 48 }}>
          載入中…
        </div>
      )}

      {connectors && connectors.length === 0 && (
        <div className="card card-pad" style={{ color: 'var(--fg-3)', textAlign: 'center', padding: 48 }}>
          尚未連接任何來源，點擊上方「<strong>新增來源</strong>」開始使用。
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
              onEdit={() => openModal({ kind: 'editSource', connectorId: c.id })}
              onReauthorize={c.platform_name === 'yuanta' ? () => handleReauthorize(c) : undefined}
              deleting={deleteMut.isPending && deleteMut.variables === c.id}
              busy={(refreshMut.isPending && refreshMut.variables === c.id) || (isYuantaFetching && c.platform_name === 'yuanta')}
              reauthorizing={reauthorizingId === c.id}
              isDemo={isDemo}
            />
          ))}
        </div>
      )}
    </div>
  )
}
