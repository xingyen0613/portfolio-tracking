import { Icon } from '../Icon'

/**
 * Manual entry / Schwab placeholder. UI only — no backend support in v1.
 */
export default function ManualForm() {
  return (
    <>
      <div className="field">
        <label className="field-label">Source name</label>
        <input className="input" placeholder="e.g. Apartment in Taipei" disabled style={{ opacity: 0.6 }} />
      </div>
      <div className="field">
        <label className="field-label">Asset class</label>
        <select className="select" disabled style={{ opacity: 0.6 }}>
          <option>Real estate</option>
          <option>Private equity</option>
          <option>Cash</option>
          <option>Other</option>
        </select>
      </div>
      <div className="field-row">
        <div className="field">
          <label className="field-label">Value</label>
          <input className="input mono" placeholder="0.00" disabled style={{ opacity: 0.6 }} />
        </div>
        <div className="field">
          <label className="field-label">Currency</label>
          <select className="select" disabled style={{ opacity: 0.6 }}>
            <option>USD</option>
            <option>TWD</option>
            <option>EUR</option>
          </select>
        </div>
      </div>
      <div className="field">
        <label className="field-label">Or upload CSV</label>
        <button
          type="button"
          className="btn btn-outline"
          disabled
          style={{ width: '100%', justifyContent: 'center', padding: 14, opacity: 0.6 }}
        >
          <Icon name="upload" /> Upload CSV / XLSX
        </button>
      </div>
      <div className="field-hint" style={{ color: 'var(--c-crypto)' }}>
        Manual entry is coming in v2 — UI is shown for preview only.
      </div>
    </>
  )
}
