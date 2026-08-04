import { Icon } from '../Icon'

/**
 * Charles Schwab placeholder. UI only — no backend support yet.
 * 手動 CSV 來源已獨立為 CsvSourceForm，不再共用這個表單。
 */
export default function ManualForm() {
  return (
    <>
      <div className="field">
        <label className="field-label">來源名稱</label>
        <input className="input" placeholder="例如：台北市的公寓" disabled style={{ opacity: 0.6 }} />
      </div>
      <div className="field">
        <label className="field-label">資產類別</label>
        <select className="select" disabled style={{ opacity: 0.6 }}>
          <option>不動產</option>
          <option>私募股權</option>
          <option>現金</option>
          <option>其他</option>
        </select>
      </div>
      <div className="field-row">
        <div className="field">
          <label className="field-label">金額</label>
          <input className="input mono" placeholder="0.00" disabled style={{ opacity: 0.6 }} />
        </div>
        <div className="field">
          <label className="field-label">幣別</label>
          <select className="select" disabled style={{ opacity: 0.6 }}>
            <option>USD</option>
            <option>TWD</option>
            <option>EUR</option>
          </select>
        </div>
      </div>
      <div className="field">
        <label className="field-label">或上傳 CSV</label>
        <button
          type="button"
          className="btn btn-outline"
          disabled
          style={{ width: '100%', justifyContent: 'center', padding: 14, opacity: 0.6 }}
        >
          <Icon name="upload" /> 上傳 CSV / XLSX
        </button>
      </div>
      <div className="field-hint" style={{ color: 'var(--c-crypto)' }}>
        Charles Schwab 連接功能尚未推出，目前僅供預覽介面。
        若要自行輸入資產金額，請改用「其他」分類中的「手動輸入」來源。
      </div>
    </>
  )
}
