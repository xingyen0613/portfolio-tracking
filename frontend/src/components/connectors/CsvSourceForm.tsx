import { useCallback, useState } from 'react'
import { Icon } from '../Icon'

/**
 * Manual CSV source. No credentials — the user optionally attaches a CSV
 * (date + amount) right here; it is imported straight after the source is
 * created. Skipping it just creates an empty source that can be filled later
 * from the 來源 page.
 */
interface Props {
  file: File | null
  setFile: (f: File | null) => void
  currency: 'USD' | 'TWD'
  setCurrency: (c: 'USD' | 'TWD') => void
  disabled?: boolean
}

export default function CsvSourceForm({
  file, setFile, currency, setCurrency, disabled,
}: Props) {
  const [isDragging, setIsDragging] = useState(false)

  const handleFile = useCallback((f: File | undefined | null) => {
    if (f?.name.toLowerCase().endsWith('.csv')) setFile(f)
  }, [setFile])

  return (
    <>
      <div className="field">
        <label className="field-label">CSV 檔案（選填）</label>
        <div
          onDragOver={e => { e.preventDefault(); setIsDragging(true) }}
          onDragLeave={e => { e.preventDefault(); setIsDragging(false) }}
          onDrop={e => {
            e.preventDefault()
            setIsDragging(false)
            if (!disabled) handleFile(e.dataTransfer.files[0])
          }}
          style={{
            position: 'relative',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 6,
            padding: '18px 12px',
            borderRadius: 8,
            border: `2px dashed ${isDragging ? 'var(--c-accent)' : 'var(--bdr)'}`,
            background: isDragging ? 'rgba(var(--c-accent-rgb, 99,102,241),0.06)' : 'var(--surf-2)',
            cursor: disabled ? 'not-allowed' : 'pointer',
            opacity: disabled ? 0.6 : 1,
            transition: 'border-color 0.15s, background 0.15s',
          }}
        >
          <input
            type="file"
            accept=".csv,text/csv"
            disabled={disabled}
            onChange={e => handleFile(e.target.files?.[0])}
            style={{
              position: 'absolute', inset: 0, opacity: 0,
              cursor: disabled ? 'not-allowed' : 'pointer',
              width: '100%', height: '100%',
            }}
          />
          <Icon name="upload" />
          <span style={{ fontSize: 13, color: file ? 'var(--fg)' : 'var(--fg-2)', pointerEvents: 'none' }}>
            {file ? file.name : '拖曳 CSV 至此或點擊瀏覽'}
          </span>
          {file && (
            <span style={{ fontSize: 11, color: 'var(--fg-3)', pointerEvents: 'none' }}>
              {(file.size / 1024).toFixed(1)} KB
            </span>
          )}
        </div>
        <div className="field-hint">
          現在不上傳也沒關係，之後可以到「來源」頁面隨時匯入。
        </div>
      </div>

      {file && (
        <div className="field">
          <label className="field-label">CSV 金額幣別</label>
          <select
            className="select"
            value={currency}
            disabled={disabled}
            onChange={e => setCurrency(e.target.value as 'USD' | 'TWD')}
          >
            <option value="TWD">TWD（新台幣，自動換算為美元）</option>
            <option value="USD">USD（美元）</option>
          </select>
        </div>
      )}

      <div
        style={{
          padding: '10px 12px',
          borderRadius: 8,
          background: 'var(--surf-2)',
          border: '1px solid var(--bdr)',
          fontSize: 12,
          color: 'var(--fg-2)',
          lineHeight: 1.6,
        }}
      >
        <div style={{ fontWeight: 600, color: 'var(--fg)', marginBottom: 4 }}>CSV 格式</div>
        <code style={{ display: 'block', color: 'var(--fg-3)', fontSize: 11 }}>
          date,total_value{'\n'}
          2026-01-01,1500000{'\n'}
          2026-02-01,1520000
        </code>
        <div style={{ marginTop: 6 }}>
          需包含 <code>date</code>（YYYY-MM-DD）與 <code>total_value</code> 兩欄，最多 5,000 筆 · 5 MB。
          沒有資料的日期會沿用最近一筆金額，因此只需在估值變動時新增一列。
        </div>
      </div>
    </>
  )
}
