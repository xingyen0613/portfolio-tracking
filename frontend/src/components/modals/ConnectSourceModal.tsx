import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { Icon } from '../Icon'
import { createConnector, type ConnectorCreatePayload } from '../../api/connectors'
import { getTemplate } from '../../data/sourceTemplates'
import type { ModalState } from '../../App'

interface Props {
  templateId: string
  close: () => void
  setModal: (m: ModalState | null) => void
}

interface FormState {
  accountLabel: string
  credentials: Record<string, string>
}

/**
 * Slice 3 ships a minimal `apikey` form so the end-to-end POST → try-fetch flow
 * is testable. Slice 4 will replace `<FormBody>` with per-auth-method components
 * (address/ibkr/email/manual).
 */
function FormBody({
  authMethod,
  state,
  setState,
  showOkxPassphrase,
}: {
  authMethod: string
  state: FormState
  setState: (next: FormState) => void
  showOkxPassphrase: boolean
}) {
  const setCred = (key: string, value: string) =>
    setState({ ...state, credentials: { ...state.credentials, [key]: value } })

  if (authMethod === 'apikey') {
    return (
      <>
        <div className="field">
          <label className="field-label">API Key</label>
          <input
            className="input mono"
            placeholder="Paste read-only API key"
            value={state.credentials.api_key ?? ''}
            onChange={e => setCred('api_key', e.target.value)}
          />
        </div>
        <div className="field">
          <label className="field-label">API Secret</label>
          <input
            className="input mono"
            type="password"
            placeholder="••••••••••••••••"
            value={state.credentials.secret ?? ''}
            onChange={e => setCred('secret', e.target.value)}
          />
        </div>
        {showOkxPassphrase && (
          <div className="field">
            <label className="field-label">Passphrase</label>
            <input
              className="input mono"
              type="password"
              placeholder="••••••••"
              value={state.credentials.passphrase ?? ''}
              onChange={e => setCred('passphrase', e.target.value)}
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

  return (
    <div className="card card-pad" style={{ color: 'var(--fg-3)' }}>
      Form for <strong>{authMethod}</strong> coming in Slice 4.
    </div>
  )
}

export default function ConnectSourceModal({ templateId, close, setModal }: Props) {
  const t = getTemplate(templateId)
  const qc = useQueryClient()

  const [state, setState] = useState<FormState>({
    accountLabel: t ? `${t.name} — Main` : 'Main',
    credentials: {},
  })
  const [error, setError] = useState<string | null>(null)
  const [warning, setWarning] = useState<string | null>(null)

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
          // Credential saved, but try-fetch failed
          setWarning(
            `Credentials saved but the initial sync failed: ${typeof detail === 'object' ? detail?.fetch_error : detail}. ` +
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

  const handleSubmit = () => {
    setError(null)
    setWarning(null)
    if (!state.accountLabel.trim()) {
      setError('Connection name is required.')
      return
    }
    mut.mutate({
      platform_name: t.id,
      account_label: state.accountLabel.trim(),
      credentials: state.credentials,
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
            value={state.accountLabel}
            onChange={e => setState({ ...state, accountLabel: e.target.value })}
          />
          <div className="field-hint">
            Helps you tell multiple {t.name} accounts apart. Must be unique within {t.name}.
          </div>
        </div>

        <FormBody
          authMethod={t.auth}
          state={state}
          setState={setState}
          showOkxPassphrase={t.id === 'okx' || t.id === 'coinbase'}
        />

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
          disabled={mut.isPending}
        >
          {mut.isPending ? 'Connecting…' : 'Connect & sync'}
        </button>
      </div>
    </div>
  )
}
