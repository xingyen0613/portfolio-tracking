import { useState } from 'react'
import { Icon } from '../Icon'
import MaskedInput from '../MaskedInput'
import { initiateYuantaOAuth } from '../../api/connectors'

interface Props {
  initialGmailAddress?: string
  initialPdfPassword?: string
}

export default function YuantaForm({ initialGmailAddress = '', initialPdfPassword = '' }: Props) {
  const [gmailAddress, setGmailAddress] = useState(initialGmailAddress)
  const [pdfPassword, setPdfPassword] = useState(initialPdfPassword)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleAuthorize = async () => {
    if (!pdfPassword.trim()) {
      setError('請輸入 PDF 解密密碼。')
      return
    }
    setError(null)
    setLoading(true)
    try {
      const { authorize_url } = await initiateYuantaOAuth(
        pdfPassword.trim(),
        gmailAddress.trim() || undefined,
      )
      window.location.href = authorize_url
    } catch (err: unknown) {
      const detail =
        err instanceof Error && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : null
      setError(detail ?? '無法取得 Google 授權連結，請稍後再試。')
      setLoading(false)
    }
  }

  return (
    <>
      <div className="field">
        <label className="field-label">收取對帳單的 Gmail 信箱</label>
        <input
          className="input"
          type="email"
          placeholder="example@gmail.com"
          value={gmailAddress}
          onChange={e => setGmailAddress(e.target.value)}
          disabled={loading}
        />
        <div className="field-hint">
          元大對帳單寄送的目標 Gmail。可以與登入本系統的 Google 帳號不同。
        </div>
      </div>

      <div className="field">
        <label className="field-label">PDF 解密密碼</label>
        <MaskedInput
          className="input mono"
          placeholder="通常為身分證字號"
          value={pdfPassword}
          onChange={setPdfPassword}
          disabled={loading}
        />
        <div className="field-hint">
          元大對帳單 PDF 的解密密碼，通常是身分證字號（大寫英文字母 + 數字）。
        </div>
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
          <Icon name="info" /> 授權後將發生什麼
        </div>
        點下方按鈕後會跳到 Google 授權頁面，請選擇上方填寫的 Gmail 帳號完成授權。授權後系統會自動讀取該 Gmail 中的元大對帳單（僅讀取，不會傳送任何 email）。
      </div>

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

      <button
        className="btn btn-primary"
        style={{ width: '100%', marginTop: 4 }}
        onClick={handleAuthorize}
        disabled={loading}
      >
        {loading ? '跳轉中…' : '授權 Gmail 並連接'}
      </button>
    </>
  )
}
