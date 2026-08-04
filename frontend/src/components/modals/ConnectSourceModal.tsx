import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useDemo } from '../../context/DemoContext'
import { redirectToEcpayCheckout, useEntitlement } from '../../api/billing'
import axios from 'axios'
import { Icon } from '../Icon'
import {
  createConnector,
  importHistoricalData,
  type ConnectorCreatePayload,
  type ConnectorCreateResponse,
  type ImportHistoryResult,
} from '../../api/connectors'
import { getTemplate } from '../../data/sourceTemplates'
import ApiKeyForm from '../connectors/ApiKeyForm'
import AddressForm from '../connectors/AddressForm'
import IBKRForm from '../connectors/IBKRForm'
import SinopacForm from '../connectors/SinopacForm'
import FubonForm from '../connectors/FubonForm'
import YuantaForm from '../connectors/YuantaForm'
import EmailForm from '../connectors/EmailForm'
import ManualForm from '../connectors/ManualForm'
import CsvSourceForm from '../connectors/CsvSourceForm'
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

  const [accountLabel, setAccountLabel] = useState(
    t ? (t.auth === 'csv' ? '' : `${t.name} — 主帳戶`) : '主帳戶',
  )
  const [credentials, setCredentials] = useState<Record<string, unknown>>({})
  const [error, setError] = useState<string | null>(null)
  const [warning, setWarning] = useState<string | null>(null)
  const [showGetApi, setShowGetApi] = useState(false)
  const [demoFlash, setDemoFlash] = useState(false)
  const [subFlash, setSubFlash] = useState(false)
  const [subscribing, setSubscribing] = useState(false)
  // CSV 來源：可在建立來源的同時直接附上檔案（選填）
  const [csvFile, setCsvFile] = useState<File | null>(null)
  const [csvCurrency, setCsvCurrency] = useState<'USD' | 'TWD'>('TWD')

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
    | {
        fetchStatus: 'success' | 'partial' | 'pending'
        // 只有 CSV 來源會帶：附檔匯入的結果，或匯入失敗的原因
        importResult?: ImportHistoryResult
        importError?: string
      }
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
    mutationFn: async (payload: ConnectorCreatePayload) => {
      const created = await createConnector(payload)
      if (!csvFile) return { created }
      // 新來源必然沒有既有資料，直接用 skip 策略匯入，不必先跑衝突檢查。
      // 匯入失敗不推翻已建立的來源 —— 回報後讓使用者到「來源」頁重試即可。
      try {
        const imported = await importHistoricalData(
          created.connector.id, csvFile, csvCurrency, 'skip',
        )
        return { created, imported }
      } catch (err) {
        let msg = err instanceof Error ? err.message : '未知錯誤'
        if (axios.isAxiosError(err)) {
          const detail = err.response?.data?.detail
          msg = typeof detail === 'string' ? detail : err.message
        }
        return { created, importError: msg }
      }
    },
    onSuccess: ({ created, imported, importError }: {
      created: ConnectorCreateResponse
      imported?: ImportHistoryResult
      importError?: string
    }) => {
      invalidateAll()
      setSuccess({
        fetchStatus:
          created.fetch_status === 'success' || created.fetch_status === 'partial'
            ? created.fetch_status
            : 'pending',
        importResult: imported,
        importError,
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
  // CSV 來源沒有憑證、也沒有同步動作，文案要改成「建立來源」而非「連接並同步」
  const isCsv = t.auth === 'csv'

  if (mut.isPending && !success) {
    return (
      <div className="modal">
        <div className="modal-head">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div className="platform-abbr" style={{ background: t.color, color: t.textColor }}>
              {t.abbr}
            </div>
            <div>
              <div className="modal-title">
                {isCsv ? `建立 ${t.name} 中…` : `背景同步 ${t.name} 中…`}
              </div>
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
            {isCsv ? (
              <>
                <div style={{ fontWeight: 600, marginBottom: 6 }}>
                  {csvFile ? '正在匯入 CSV' : '正在建立來源'}
                </div>
                {csvFile
                  ? '系統正在解析檔案並重算歷史走勢，資料跨度較大時可能需要數十秒，請勿關閉此視窗。'
                  : '馬上就好。'}
              </>
            ) : (
              <>
                <div style={{ fontWeight: 600, marginBottom: 6 }}>首次同步進行中</div>
                系統正在抓取餘額。錢包同步會平行查詢每條鏈，可能需要 10–30 秒。
                <div style={{ marginTop: 8, color: 'var(--fg-2)' }}>
                  您可以關閉此視窗，同步會在背景繼續進行，完成後 Dashboard 會自動更新。
                </div>
              </>
            )}
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
    // 來源建立成功但附檔匯入失敗，也要走警示色
    const isWarn = isPending || isPartial || !!success.importError
    const accentColor  = isWarn ? 'var(--c-crypto)' : 'var(--c-pos)'
    const accentBg     = isWarn ? 'rgba(240,162,60,0.10)' : 'rgba(46,184,138,0.10)'
    const accentBorder = isWarn ? 'rgba(240,162,60,0.35)' : 'rgba(46,184,138,0.35)'
    const heading = isCsv
      ? success.importError
        ? `${t.name} 已建立 — CSV 匯入失敗`
        : `${t.name} 已建立`
      : isPending
        ? `${t.name} 已新增 — 首次同步仍在進行`
        : isPartial
          ? `${t.name} 已新增，部分資料不完整`
          : `${t.name} 已連接`
    const imp = success.importResult
    const message = isCsv
      ? success.importError
        ? `來源已建立，但 CSV 匯入失敗：${success.importError}　可到「來源」頁面點上傳圖示重試。`
        : imp
          ? `已從 CSV 匯入 ${imp.written_count} 筆` +
            (imp.date_from && imp.date_to ? `（${imp.date_from} → ${imp.date_to}）` : '') +
            '。最後一筆之後的日期會沿用該金額，資產現在會顯示在 Dashboard。' +
            (imp.invalid_rows.length > 0 ? `　有 ${imp.invalid_rows.length} 列無法解析已略過。` : '')
          : '來源已建立，目前還沒有資料。請到「來源」頁面點擊此來源的「匯入歷史紀錄」上傳 CSV。'
      : isPending
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
      setError('請輸入來源名稱。')
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
            <div className="modal-title">{isCsv ? '新增' : '連接'} {t.name}</div>
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
            <label className="field-label">來源名稱</label>
            <input
              className="input"
              placeholder={isCsv ? '例如：台北市的公寓' : `${t.name} — 主帳戶`}
              value={accountLabel}
              onChange={e => setAccountLabel(e.target.value)}
              disabled={!canSubmit}
            />
            <div className="field-hint">
              {isCsv
                ? '這個名稱會顯示在資產清單，例如「台北市的公寓」「儲蓄險」。手動來源之間需唯一。'
                : `方便您區分多個 ${t.name} 帳戶，同一個 ${t.name} 底下需唯一。`}
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
        {t.auth === 'csv' && (
          <CsvSourceForm
            file={csvFile}
            setFile={setCsvFile}
            currency={csvCurrency}
            setCurrency={setCsvCurrency}
            disabled={!canSubmit}
          />
        )}

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
                  {isCsv ? '建立來源' : '連接並同步'}
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
                  {isCsv ? '建立來源' : '連接並同步'}
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
                {mut.isPending
                  ? (isCsv ? '建立中…' : '連接中…')
                  : canSubmit
                    ? (isCsv ? (csvFile ? '建立並匯入' : '建立來源') : '連接並同步')
                    : '即將推出'}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
