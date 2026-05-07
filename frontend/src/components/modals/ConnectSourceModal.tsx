import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { Icon } from '../Icon'
import { createConnector, type ConnectorCreatePayload } from '../../api/connectors'
import { getTemplate } from '../../data/sourceTemplates'
import ApiKeyForm from '../connectors/ApiKeyForm'
import AddressForm from '../connectors/AddressForm'
import IBKRForm from '../connectors/IBKRForm'
import EmailForm from '../connectors/EmailForm'
import ManualForm from '../connectors/ManualForm'
import type { ModalState } from '../../App'

interface Props {
  templateId: string
  close: () => void
  setModal: (m: ModalState | null) => void
}

export default function ConnectSourceModal({ templateId, close, setModal }: Props) {
  const t = getTemplate(templateId)
  const qc = useQueryClient()

  const [accountLabel, setAccountLabel] = useState(t ? `${t.name} — Main` : 'Main')
  const [credentials, setCredentials] = useState<Record<string, unknown>>({})
  const [error, setError] = useState<string | null>(null)
  const [warning, setWarning] = useState<string | null>(null)

  const setCredential = (key: string, value: unknown) =>
    setCredentials(prev => ({ ...prev, [key]: value }))

  const mut = useMutation({
    mutationFn: (payload: ConnectorCreatePayload) => createConnector(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['connectors'] })
      qc.invalidateQueries({ queryKey: ['holdings'] })
      qc.invalidateQueries({ queryKey: ['portfolio/history'] })
      qc.invalidateQueries({ queryKey: ['portfolio/allocation'] })
      close()
    },
    onError: (err: unknown) => {
      if (axios.isAxiosError(err)) {
        const status = err.response?.status
        const detail = err.response?.data?.detail
        if (status === 502) {
          const fetchErr = typeof detail === 'object' && detail
            ? (detail as { fetch_error?: string }).fetch_error
            : detail
          setWarning(
            `Credentials saved but the initial sync failed: ${fetchErr ?? 'unknown error'}. ` +
              'The next scheduled sync will try again — you can also click Refresh from Sources.',
          )
          qc.invalidateQueries({ queryKey: ['connectors'] })
          return
        }
        if (typeof detail === 'string') {
          setError(detail)
          return
        }
        setError(err.message)
        return
      }
      setError(err instanceof Error ? err.message : 'Unknown error')
    },
  })

  if (!t) {
    return (
      <div className="modal" style={{ padding: 20 }}>
        <div className="modal-head">
          <div className="modal-title">Unknown source</div>
          <button className="modal-close" onClick={close}>
            <Icon name="x" />
          </button>
        </div>
      </div>
    )
  }

  const canSubmit = t.implemented

  const handleSubmit = () => {
    setError(null)
    setWarning(null)
    if (!canSubmit) return
    if (!accountLabel.trim()) {
      setError('Connection name is required.')
      return
    }
    mut.mutate({
      platform_name: t.id,
      account_label: accountLabel.trim(),
      credentials,
    })
  }

  return (
    <div className="modal">
      <div className="modal-head">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button
            className="modal-close"
            onClick={() => setModal({ kind: 'addSource' })}
            title="Back"
          >
            <Icon name="chevronL" />
          </button>
          <div className="platform-abbr" style={{ background: t.color, color: t.textColor }}>
            {t.abbr}
          </div>
          <div>
            <div className="modal-title">Connect {t.name}</div>
            <div className="modal-sub">{t.desc}</div>
          </div>
        </div>
        <button className="modal-close" onClick={close}>
          <Icon name="x" />
        </button>
      </div>

      <div className="modal-body">
        <div className="field">
          <label className="field-label">Connection name</label>
          <input
            className="input"
            placeholder={`${t.name} — Main`}
            value={accountLabel}
            onChange={e => setAccountLabel(e.target.value)}
            disabled={!canSubmit}
          />
          <div className="field-hint">
            Helps you tell multiple {t.name} accounts apart. Must be unique within {t.name}.
          </div>
        </div>

        {t.auth === 'apikey' && (
          <ApiKeyForm credentials={credentials} setCredential={setCredential} template={t} />
        )}
        {t.auth === 'address' && (
          <AddressForm credentials={credentials} setCredential={setCredential} template={t} />
        )}
        {t.auth === 'ibkr' && (
          <IBKRForm credentials={credentials} setCredential={setCredential} />
        )}
        {t.auth === 'email' && <EmailForm template={t} />}
        {t.auth === 'manual' && <ManualForm />}

        {error && (
          <div
            style={{
              padding: 10,
              borderRadius: 8,
              background: 'rgba(236,91,126,0.08)',
              border: '1px solid rgba(236,91,126,0.3)',
              color: 'var(--c-neg)',
              fontSize: 12,
            }}
          >
            {error}
          </div>
        )}
        {warning && (
          <div
            style={{
              padding: 10,
              borderRadius: 8,
              background: 'rgba(240,162,60,0.08)',
              border: '1px solid rgba(240,162,60,0.3)',
              color: 'var(--c-crypto)',
              fontSize: 12,
            }}
          >
            {warning}
          </div>
        )}
      </div>

      <div className="modal-foot">
        <button className="btn btn-ghost" onClick={close} disabled={mut.isPending}>
          Cancel
        </button>
        <button
          className="btn btn-primary"
          onClick={handleSubmit}
          disabled={mut.isPending || !canSubmit}
        >
          {mut.isPending ? 'Connecting…' : canSubmit ? 'Connect & sync' : 'Coming soon'}
        </button>
      </div>
    </div>
  )
}
