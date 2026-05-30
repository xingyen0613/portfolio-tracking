import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { Icon } from '../Icon'
import {
  getConnectorCredentials,
  listConnectors,
  updateConnector,
  type ConnectorUpdatePayload,
} from '../../api/connectors'
import { getTemplate } from '../../data/sourceTemplates'
import ApiKeyForm from '../connectors/ApiKeyForm'
import AddressForm from '../connectors/AddressForm'
import IBKRForm from '../connectors/IBKRForm'
import SinopacForm from '../connectors/SinopacForm'
import YuantaForm from '../connectors/YuantaForm'

interface Props {
  connectorId: string
  close: () => void
}

export default function EditSourceModal({ connectorId, close }: Props) {
  const qc = useQueryClient()

  const { data: connectors } = useQuery({ queryKey: ['connectors'], queryFn: listConnectors })
  const connector = connectors?.find(c => c.id === connectorId)
  const t = getTemplate(connector?.platform_name ?? '')

  const { data: existingCreds, isLoading: credsLoading } = useQuery({
    queryKey: ['connector-credentials', connectorId],
    queryFn: () => getConnectorCredentials(connectorId),
    enabled: !!connector && t?.auth !== 'yuanta',
  })

  const [accountLabel, setAccountLabel] = useState('')
  const [credentials, setCredentials] = useState<Record<string, unknown>>({})
  const [credentialsReady, setCredentialsReady] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (connector?.account_label) setAccountLabel(connector.account_label)
  }, [connector])

  useEffect(() => {
    if (existingCreds && !credentialsReady) {
      setCredentials(existingCreds)
      setCredentialsReady(true)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [existingCreds])

  const setCredential = (key: string, value: unknown) =>
    setCredentials(prev => ({ ...prev, [key]: value }))

  const mut = useMutation({
    mutationFn: (payload: ConnectorUpdatePayload) => updateConnector(connectorId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['connectors'] })
      close()
    },
    onError: (err: unknown) => {
      if (axios.isAxiosError(err)) {
        const detail = err.response?.data?.detail
        setError(typeof detail === 'string' ? detail : err.message)
      } else {
        setError(err instanceof Error ? err.message : 'Unknown error')
      }
    },
  })

  if (!connector || !t) {
    return (
      <div className="modal" style={{ padding: 20 }}>
        <div className="modal-head">
          <div className="modal-title">Loading…</div>
          <button className="modal-close" onClick={close}><Icon name="x" /></button>
        </div>
      </div>
    )
  }

  // Yuanta uses its own OAuth re-auth flow
  if (t.auth === 'yuanta') {
    return (
      <div className="modal">
        <div className="modal-head">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div className="platform-abbr" style={{ background: t.color, color: t.textColor }}>
              {t.abbr}
            </div>
            <div>
              <div className="modal-title">重新授權 {t.name}</div>
              <div className="modal-sub">{t.desc}</div>
            </div>
          </div>
          <button className="modal-close" onClick={close}><Icon name="x" /></button>
        </div>
        <div className="modal-body">
          <YuantaForm />
        </div>
      </div>
    )
  }

  const handleSubmit = () => {
    setError(null)
    if (!accountLabel.trim()) {
      setError('Connection name is required.')
      return
    }
    mut.mutate({ account_label: accountLabel.trim(), credentials })
  }

  const needsCredsLoad = t.auth !== 'manual' && t.auth !== 'email' && t.auth !== 'yuanta'
  const isLoading = needsCredsLoad && (credsLoading || !credentialsReady)

  return (
    <div className="modal">
      <div className="modal-head">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div className="platform-abbr" style={{ background: t.color, color: t.textColor }}>
            {t.abbr}
          </div>
          <div>
            <div className="modal-title">Edit {t.name}</div>
            <div className="modal-sub">{t.desc}</div>
          </div>
        </div>
        <button className="modal-close" onClick={close}><Icon name="x" /></button>
      </div>

      <div className="modal-body">
        {isLoading ? (
          <div style={{ color: 'var(--fg-3)', textAlign: 'center', padding: 24 }}>Loading…</div>
        ) : (
          <>
            <div className="field">
              <label className="field-label">Connection name</label>
              <input
                className="input"
                value={accountLabel}
                onChange={e => setAccountLabel(e.target.value)}
                disabled={mut.isPending}
              />
            </div>

            <div
              style={{
                padding: '8px 12px',
                borderRadius: 8,
                background: 'rgba(255,255,255,0.04)',
                border: '1px solid var(--bdr)',
                fontSize: 11,
                color: 'var(--fg-3)',
                marginBottom: 4,
              }}
            >
              Secret fields are not pre-filled. Leave them blank to keep the current value.
            </div>

            {t.auth === 'apikey' && (
              <ApiKeyForm key={connectorId} credentials={credentials} setCredential={setCredential} template={t} />
            )}
            {t.auth === 'address' && (
              <AddressForm key={connectorId} credentials={credentials} setCredential={setCredential} template={t} />
            )}
            {t.auth === 'ibkr' && (
              <IBKRForm key={connectorId} credentials={credentials} setCredential={setCredential} />
            )}
            {t.auth === 'sinopac' && (
              <SinopacForm key={connectorId} credentials={credentials} setCredential={setCredential} />
            )}

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
          </>
        )}
      </div>

      <div className="modal-foot">
        <button className="btn btn-ghost" onClick={close} disabled={mut.isPending}>
          Cancel
        </button>
        <button
          className="btn btn-primary"
          onClick={handleSubmit}
          disabled={mut.isPending || isLoading}
        >
          {mut.isPending ? 'Saving…' : 'Save changes'}
        </button>
      </div>
    </div>
  )
}
