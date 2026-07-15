import { useRef, useState } from 'react'
import { Icon } from '../Icon'
import MaskedInput from '../MaskedInput'

interface Props {
  credentials: Record<string, unknown>
  setCredential: (key: string, value: unknown) => void
}

export default function FubonForm({ credentials, setCredential }: Props) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [certName, setCertName] = useState<string | null>(null)
  const [certError, setCertError] = useState<string | null>(null)

  const handleFile = (file: File | undefined) => {
    setCertError(null)
    if (!file) return
    if (file.size > 100 * 1024) {
      setCertError('憑證檔案過大（>100KB），請確認選的是 .pfx 憑證檔。')
      return
    }
    const reader = new FileReader()
    reader.onload = () => {
      const bytes = new Uint8Array(reader.result as ArrayBuffer)
      let binary = ''
      for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i])
      setCredential('cert_pfx_b64', btoa(binary))
      setCertName(`${file.name} (${(file.size / 1024).toFixed(1)} KB)`)
    }
    reader.onerror = () => setCertError('讀取憑證檔失敗，請重試。')
    reader.readAsArrayBuffer(file)
  }

  return (
    <>
      <div className="field">
        <label className="field-label">身分證字號</label>
        <MaskedInput
          className="input mono"
          placeholder="A123456789"
          value={(credentials.fubon_id as string) ?? ''}
          onChange={v => setCredential('fubon_id', v)}
        />
        <div className="field-hint">富邦多因子登入的第一因子，僅用於查詢你的帳戶。</div>
      </div>
      <div className="field">
        <label className="field-label">API Key</label>
        <MaskedInput
          className="input mono"
          placeholder="Paste your Fubon API key"
          value={(credentials.api_key as string) ?? ''}
          onChange={v => setCredential('api_key', v)}
        />
        <div className="field-hint">
          富邦官網 → 新一代 API → 金鑰申請及管理 → 新增金鑰。權限請只勾「查詢」，勿開下單。
        </div>
      </div>
      <div className="field">
        <label className="field-label">電子交易憑證（.pfx）</label>
        <input
          ref={fileRef}
          type="file"
          accept=".pfx,.p12"
          style={{ display: 'none' }}
          onChange={e => handleFile(e.target.files?.[0])}
        />
        <button
          type="button"
          className="btn btn-outline"
          style={{ width: '100%', justifyContent: 'center' }}
          onClick={() => fileRef.current?.click()}
        >
          {certName ? `已選擇：${certName}` : '選擇憑證檔案'}
        </button>
        <div className="field-hint">
          在富邦金鑰管理頁申請「網頁憑證」並匯出 .pfx。憑證會加密儲存，僅用於查詢登入。
        </div>
        {certError && (
          <div className="field-hint" style={{ color: 'var(--c-neg)' }}>{certError}</div>
        )}
      </div>
      <div className="field">
        <label className="field-label">憑證密碼（選填）</label>
        <MaskedInput
          className="input mono"
          placeholder="留空 = 預設密碼（身分證字號）"
          value={(credentials.cert_password as string) ?? ''}
          onChange={v => setCredential('cert_password', v)}
        />
      </div>

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
          <Icon name="info" /> Read-only by design
        </div>
        本系統只查詢持倉與現金餘額，不下單、不轉帳。你的電子平台密碼從不經手本系統；
        API Key 請設定「僅查詢」權限，即使外洩也無法下單或出金。
      </div>
    </>
  )
}
