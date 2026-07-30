import { Icon } from '../Icon'
import MaskedInput from '../MaskedInput'

interface Props {
  credentials: Record<string, unknown>
  setCredential: (key: string, value: unknown) => void
}

export default function SinopacForm({ credentials, setCredential }: Props) {
  return (
    <>
      <div className="field">
        <label className="field-label">API Key</label>
        <MaskedInput
          className="input mono"
          placeholder="貼上您的 Shioaji API Key"
          value={(credentials.api_key as string) ?? ''}
          onChange={v => setCredential('api_key', v)}
        />
        <div className="field-hint">
          永豐 e-leader → 我的設定 → API 設定 → 新增 API Key（記得勾「正式環境」權限）。
        </div>
      </div>
      <div className="field">
        <label className="field-label">Secret Key</label>
        <MaskedInput
          className="input mono"
          placeholder="••••••••••••••••"
          value={(credentials.secret_key as string) ?? ''}
          onChange={v => setCredential('secret_key', v)}
        />
        <div className="field-hint">
          API Key 申請後一併產生。建立後請立刻複製，永豐網站不會再次顯示。
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
          <Icon name="info" /> 設計上僅唯讀
        </div>
        本系統只查詢持倉與現金餘額，不下單、不轉帳。Shioaji 下單需要額外的 CA 憑證簽章，本系統不會請求。
      </div>
    </>
  )
}
