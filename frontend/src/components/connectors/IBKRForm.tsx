import { Icon } from '../Icon'
import MaskedInput from '../MaskedInput'

interface Props {
  credentials: Record<string, unknown>
  setCredential: (key: string, value: unknown) => void
}

export default function IBKRForm({ credentials, setCredential }: Props) {
  return (
    <>
      <div className="field">
        <label className="field-label">Flex Query Token</label>
        <MaskedInput
          className="input mono"
          placeholder="貼上您的 Flex token"
          value={(credentials.flex_token as string) ?? ''}
          onChange={v => setCredential('flex_token', v)}
        />
        <div className="field-hint">
          IBKR → Settings → Account Settings → Flex Web Service → Generate token.
        </div>
      </div>
      <div className="field">
        <label className="field-label">Query ID</label>
        <input
          className="input mono"
          placeholder="例如 123456789"
          value={(credentials.query_id as string) ?? ''}
          onChange={e => setCredential('query_id', e.target.value)}
        />
        <div className="field-hint">
          建立一個包含 OpenPosition (SUMMARY) + EquitySummaryByReportDateInBase 的 Flex Query，再把它的數字 ID 貼在這裡。
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
        Flex token 無法用來下單或轉帳，僅能讀取您的投資組合報表。
      </div>
    </>
  )
}
