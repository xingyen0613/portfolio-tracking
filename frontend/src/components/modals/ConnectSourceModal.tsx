import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useDemo } from '../../context/DemoContext'
import { redirectToEcpayCheckout, useEntitlement } from '../../api/billing'
import axios from 'axios'
import { Icon } from '../Icon'
import { createConnector, type ConnectorCreatePayload } from '../../api/connectors'
import { getTemplate } from '../../data/sourceTemplates'
import ApiKeyForm from '../connectors/ApiKeyForm'
import AddressForm from '../connectors/AddressForm'
import IBKRForm from '../connectors/IBKRForm'
import SinopacForm from '../connectors/SinopacForm'
import FubonForm from '../connectors/FubonForm'
import YuantaForm from '../connectors/YuantaForm'
import EmailForm from '../connectors/EmailForm'
import ManualForm from '../connectors/ManualForm'
import GetApiModal from './GetApiModal'
import type { ModalState } from '../../App'

interface Props {
  templateId: string
  close: () => void
  setModal: (m: ModalState | null) => void
}

export default function ConnectSourceModal({ templateId, close, setModal }: Props) {
  const t = getTemplate(templateId)
  const qc = useQueryClient()
  const { isDemo } = useDemo()
  const { data: entitlement } = useEntitlement()
  // Gate only when we positively know the user is not subscribed (avoid flashing
  // the gate while loading, and while demo mode has its own gate). Backend enforces regardless.
  const subGateActive = !isDemo && entitlement !== undefined && !entitlement.active

  const [accountLabel, setAccountLabel] = useState(t ? `${t.name} — 主帳戶` : '主帳戶')
  const [credentials, setCredentials] = useState<Record<string, unknown>>({})
  const [error, setError] = useState<string | null>(null)
  const [warning, setWarning] = useState<string | null>(null)
  const [showGetApi, setShowGetApi] = useState(false)
  const [demoFlash, setDemoFlash] = useState(false)
  const [subFlash, setSubFlash] = useState(false)
  const [subscribing, setSubscribing] = useState(false)

  const goSubscribe = async () => {
    setError(null)
    setSubscribing(true)
    try {
      await redirectToEcpayCheckout()
    } catch {
      setError('無法前往綠界付款頁，請稍後再試。')
    } finally {
      // Checkout opens in a new tab, so this modal stays interactive.
      setSubscribing(false)
    }
  }
  const [success, setSuccess] = useState<
    | { fetchStatus: 'success' | 'partial' | 'pending' }
    | null
  >(null)

  const setCredential = (key: string, value: unknown) =>
    setCredentials(prev => ({ ...prev, [key]: value }))

  const invalidateAll = () => {
    qc.invalidateQueries({ queryKey: ['connectors'] })
    qc.invalidateQueries({ queryKey: ['holdings'] })
    qc.invalidateQueries({ queryKey: ['portfolio/history'] })
    qc.invalidateQueries({ queryKey: ['portfolio/allocation'] })
  }

  const mut = useMutation({
    mutationFn: (payload: ConnectorCreatePayload) => createConnector(payload),
    onSuccess: data => {
      invalidateAll()
      setSuccess({
        fetchStatus:
          data.fetch_status === 'success' || data.fetch_status === 'partial'
            ? data.fetch_status
            : 'pending',
      })
    },
    onError: (err: unknown) => {
      if (axios.isAxiosError(err)) {
        // Client-side timeout / aborted before response: the connector row was
        // saved on the backend before run_batch fired, so treat this as
        // "added; first sync still running in the background".
        const isClientTimeout =
          err.code === 'ECONNABORTED' ||
          err.code === 'ETIMEDOUT' ||
          (!err.response && /timeout/i.test(err.message))
        if (isClientTimeout) {
          invalidateAll()
          setSuccess({ fetchStatus: 'pending' })
          return
        }
        const status = err.response?.status
        const detail = err.response?.data?.detail
        if (status === 502) {
          const fetchErr = typeof detail === 'object' && detail
            ? (detail as { fetch_error?: string }).fetch_error
            : detail
          setWarning(
            `憑證已儲存，但首次同步失敗：${fetchErr ?? '未知錯誤'}。` +
              '下次排程同步會自動重試，您也可以到「來源」頁面點擊重新整理。',
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
      setError(err instanceof Error ? err.message : '未知錯誤')
    },
  })

  if (!t) {
    return (
      <div className="modal" style={{ padding: 20 }}>
        <div className="modal-head">
          <div className="modal-title">未知的來源</div>
          <button className="modal-close" onClick={close}>
            <Icon name="x" />
          </button>
        </div>
      </div>
    )
  }

  if (showGetApi && t.getApiConfig) {
    return <GetApiModal platformName={t.name} config={t.getApiConfig} onBack={() => setShowGetApi(false)} />
  }

  const canSubmit = t.implemented

  if (mut.isPending && !success) {
    return (
      <div className="modal">
        <div className="modal-head">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div className="platform-abbr" style={{ background: t.color, color: t.textColor }}>
              {t.abbr}
            </div>
            <div>
              <div className="modal-title">背景同步 {t.name} 中…</div>
              <div className="modal-sub">{t.desc}</div>
            </div>
          </div>
          <button className="modal-close" onClick={close}>
            <Icon name="x" />
          </button>
        </div>
        <div className="modal-body">
          <div
            style={{
              padding: 14,
              borderRadius: 10,
              background: 'rgba(240,162,60,0.10)',
              border: '1px solid rgba(240,162,60,0.35)',
              color: 'var(--c-crypto)',
              fontSize: 13,
              lineHeight: 1.55,
            }}
          >
            <div style={{ fontWeight: 600, marginBottom: 6 }}>首次同步進行中</div>
            系統正在抓取餘額。錢包同步會平行查詢每條鏈，可能需要 10–30 秒。
            <div style={{ marginTop: 8, color: 'var(--fg-2)' }}>
              您可以關閉此視窗，同步會在背景繼續進行，完成後 Dashboard 會自動更新。
            </div>
          </div>
        </div>
        <div className="modal-foot">
          <button className="btn btn-primary" onClick={close}>
            關閉
          </button>
        </div>
      </div>
    )
  }

  if (success) {
    const isPending = success.fetchStatus === 'pending'
    const isPartial = success.fetchStatus === 'partial'
    const accentColor = isPending
      ? 'var(--c-crypto)'
      : isPartial
        ? 'var(--c-crypto)'
        : 'var(--c-pos)'
    const accentBg = isPending
      ? 'rgba(240,162,60,0.10)'
      : isPartial
        ? 'rgba(240,162,60,0.10)'
        : 'rgba(46,184,138,0.10)'
    const accentBorder = isPending
      ? 'rgba(240,162,60,0.35)'
      : isPartial
        ? 'rgba(240,162,60,0.35)'
        : 'rgba(46,184,138,0.35)'
    const heading = isPending
      ? `${t.name} 已新增 — 首次同步仍在進行`
      : isPartial
        ? `${t.name} 已新增，部分資料不完整`
        : `${t.name} 已連接`
    const message = isPending
      ? '憑證已儲存。首次同步耗時較長，仍在背景執行中，完成後持倉會顯示在「來源」與 Dashboard。'
      : isPartial
        ? '憑證已儲存，首次同步已完成，但部分子帳戶回傳資料不完整，請至「來源」頁面查看詳情。'
        : '憑證已儲存，首次同步已成功完成，持倉現在會顯示在您的 Dashboard。'
    return (
      <div className="modal">
        <div className="modal-head">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div className="platform-abbr" style={{ background: t.color, color: t.textColor }}>
              {t.abbr}
            </div>
            <div>
              <div className="modal-title">{heading}</div>
              <div className="modal-sub">{t.desc}</div>
            </div>
          </div>
          <button className="modal-close" onClick={close}>
            <Icon name="x" />
          </button>
        </div>
        <div className="modal-body">
          <div
            style={{
              padding: 14,
              borderRadius: 10,
              background: accentBg,
              border: `1px solid ${accentBorder}`,
              color: accentColor,
              fontSize: 13,
              lineHeight: 1.5,
            }}
          >
            {message}
          </div>
        </div>
        <div className="modal-foot">
          <button className="btn btn-primary" onClick={close}>
            完成
          </button>
        </div>
      </div>
    )
  }

  const handleSubmit = () => {
    setError(null)
    setWarning(null)
    if (!canSubmit) return
    if (!accountLabel.trim()) {
      setError('請輸入連接名稱。')
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
            title="返回"
          >
            <Icon name="chevronL" />
          </button>
          <div className="platform-abbr" style={{ background: t.color, color: t.textColor }}>
            {t.abbr}
          </div>
          <div>
            <div className="modal-title">連接 {t.name}</div>
            <div className="modal-sub">{t.desc}</div>
          </div>
        </div>
        <button className="modal-close" onClick={close}>
          <Icon name="x" />
        </button>
      </div>

      <div className="modal-body">
        {t.auth !== 'yuanta' && (
          <div className="field">
            <label className="field-label">連接名稱</label>
            <input
              className="input"
              placeholder={`${t.name} — 主帳戶`}
              value={accountLabel}
              onChange={e => setAccountLabel(e.target.value)}
              disabled={!canSubmit}
            />
            <div className="field-hint">
              方便您區分多個 {t.name} 帳戶，同一個 {t.name} 底下需唯一。
            </div>
          </div>
        )}

        {t.auth === 'apikey' && (
          <ApiKeyForm credentials={credentials} setCredential={setCredential} template={t} />
        )}
        {t.auth === 'address' && (
          <AddressForm credentials={credentials} setCredential={setCredential} template={t} />
        )}
        {t.auth === 'ibkr' && (
          <IBKRForm credentials={credentials} setCredential={setCredential} />
        )}
        {t.auth === 'sinopac' && (
          <SinopacForm credentials={credentials} setCredential={setCredential} />
        )}
        {t.auth === 'fubon' && (
          <FubonForm credentials={credentials} setCredential={setCredential} />
        )}
        {t.auth === 'yuanta' && <YuantaForm />}
        {t.auth === 'email' && <EmailForm template={t} />}
        {t.auth === 'manual' && <ManualForm />}

        {t.getApiConfig?.apiWarning && (
          <div
            style={{
              padding: 10,
              borderRadius: 8,
              background: 'rgba(240,162,60,0.08)',
              border: '1px solid rgba(240,162,60,0.3)',
              color: 'var(--c-crypto)',
              fontSize: 12,
              lineHeight: 1.55,
            }}
          >
            ⚠ {t.getApiConfig.apiWarning}
          </div>
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

      {t.auth !== 'yuanta' && (
        <div
          className="modal-foot"
          style={{ justifyContent: t.getApiConfig ? 'space-between' : 'flex-end' }}
        >
          {t.getApiConfig && (
            <button
              className="btn btn-outline"
              onClick={() => setShowGetApi(true)}
              disabled={mut.isPending}
            >
              取得 API
            </button>
          )}
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-ghost" onClick={close} disabled={mut.isPending}>
              取消
            </button>
            {isDemo ? (
              <div style={{ position: 'relative', display: 'inline-block' }}>
                <button
                  className="btn btn-primary"
                  style={{ opacity: 0.55 }}
                  onClick={() => {
                    setDemoFlash(true)
                    setTimeout(() => setDemoFlash(false), 1400)
                  }}
                >
                  連接並同步
                </button>
                {demoFlash && (
                  <div style={{
                    position: 'absolute', bottom: '110%', left: '50%', transform: 'translateX(-50%)',
                    background: 'var(--surf-3)', border: '1px solid var(--bdr)',
                    borderRadius: 5, padding: '4px 10px', fontSize: 11, color: 'var(--fg-2)',
                    whiteSpace: 'nowrap', zIndex: 999, pointerEvents: 'none',
                    animation: 'demoFlash 1.4s ease forwards',
                  }}>
                    預覽模式，無法新增來源
                  </div>
                )}
              </div>
            ) : subGateActive ? (
              <div style={{ position: 'relative', display: 'inline-block' }}>
                <button
                  className="btn btn-outline"
                  onClick={goSubscribe}
                  disabled={subscribing}
                  style={{ marginRight: 8 }}
                >
                  {subscribing ? '前往訂閱…' : '前往訂閱'}
                </button>
                <button
                  className="btn btn-primary"
                  style={{ opacity: 0.55 }}
                  onClick={() => {
                    setSubFlash(true)
                    setTimeout(() => setSubFlash(false), 1400)
                  }}
                >
                  連接並同步
                </button>
                {subFlash && (
                  <div style={{
                    position: 'absolute', bottom: '110%', left: '50%', transform: 'translateX(-50%)',
                    background: 'var(--surf-3)', border: '1px solid var(--bdr)',
                    borderRadius: 5, padding: '4px 10px', fontSize: 11, color: 'var(--fg-2)',
                    whiteSpace: 'nowrap', zIndex: 999, pointerEvents: 'none',
                    animation: 'demoFlash 1.4s ease forwards',
                  }}>
                    需有效訂閱才能新增來源
                  </div>
                )}
              </div>
            ) : (
              <button
                className="btn btn-primary"
                onClick={handleSubmit}
                disabled={mut.isPending || !canSubmit}
              >
                {mut.isPending ? '連接中…' : canSubmit ? '連接並同步' : '即將推出'}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
