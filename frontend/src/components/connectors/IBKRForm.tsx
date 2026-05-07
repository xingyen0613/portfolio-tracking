import { Icon } from '../Icon'

interface Props {
  credentials: Record<string, unknown>
  setCredential: (key: string, value: unknown) => void
}

export default function IBKRForm({ credentials, setCredential }: Props) {
  return (
    <>
      <div className="field">
        <label className="field-label">Flex Query Token</label>
        <input
          className="input mono"
          placeholder="Paste your Flex token"
          value={(credentials.flex_token as string) ?? ''}
          onChange={e => setCredential('flex_token', e.target.value)}
        />
        <div className="field-hint">
          IBKR → Settings → Account Settings → Flex Web Service → Generate token.
        </div>
      </div>
      <div className="field">
        <label className="field-label">Query ID</label>
        <input
          className="input mono"
          placeholder="e.g. 123456789"
          value={(credentials.query_id as string) ?? ''}
          onChange={e => setCredential('query_id', e.target.value)}
        />
        <div className="field-hint">
          Create a Flex Query covering OpenPosition (SUMMARY) + EquitySummaryByReportDateInBase, then copy
          its numeric ID here.
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
          <Icon name="info" /> Read-only by design
        </div>
        Flex tokens cannot place trades or move funds. They expose only your portfolio reports.
      </div>
    </>
  )
}
