import { useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { Icon } from '../Icon'
import {
  type Connector,
  type ImportHistoryResult,
  importHistoricalData,
} from '../../api/connectors'
import { getTemplate } from '../../data/sourceTemplates'

interface Props {
  connector: Connector
  close: () => void
}

type Phase = 'form' | 'uploading' | 'result'

export default function ImportHistoryModal({ connector, close }: Props) {
  const qc = useQueryClient()
  const t = getTemplate(connector.platform_name)
  const abbr = t?.abbr ?? connector.platform_name.slice(0, 3).toUpperCase()
  const name = t?.name ?? connector.platform_name
  const color = t?.color ?? '#3a3a44'
  const textColor = t?.textColor ?? '#fff'

  const fileRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [currency, setCurrency] = useState<'USD' | 'TWD'>('USD')
  const [conflictStrategy, setConflictStrategy] = useState<'skip' | 'override'>('skip')
  const [phase, setPhase] = useState<Phase>('form')
  const [result, setResult] = useState<ImportHistoryResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const mut = useMutation({
    mutationFn: () => importHistoricalData(connector.id, file!, currency, conflictStrategy),
    onMutate: () => {
      setPhase('uploading')
      setError(null)
    },
    onSuccess: data => {
      qc.invalidateQueries({ queryKey: ['portfolio/history'] })
      qc.invalidateQueries({ queryKey: ['portfolio/allocation'] })
      setResult(data)
      setPhase('result')
    },
    onError: (err: unknown) => {
      setPhase('form')
      if (axios.isAxiosError(err)) {
        const detail = err.response?.data?.detail
        setError(typeof detail === 'string' ? detail : err.message)
      } else {
        setError(err instanceof Error ? err.message : 'Upload failed')
      }
    },
  })

  // ── uploading ──────────────────────────────────────────────────────────
  if (phase === 'uploading') {
    return (
      <div className="modal">
        <div className="modal-head">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div className="platform-abbr" style={{ background: color, color: textColor }}>
              {abbr}
            </div>
            <div className="modal-title">Importing history…</div>
          </div>
        </div>
        <div className="modal-body">
          <div
            style={{
              padding: 14, borderRadius: 10,
              background: 'rgba(240,162,60,0.10)',
              border: '1px solid rgba(240,162,60,0.35)',
              color: 'var(--c-crypto)', fontSize: 13, lineHeight: 1.55,
            }}
          >
            Uploading and processing your CSV. This may take a few seconds for large files.
          </div>
        </div>
      </div>
    )
  }

  // ── result ─────────────────────────────────────────────────────────────
  if (phase === 'result' && result) {
    const hasSkipped = result.skipped_count > 0
    const hasInvalid = result.invalid_rows.length > 0
    return (
      <div className="modal">
        <div className="modal-head">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div className="platform-abbr" style={{ background: color, color: textColor }}>
              {abbr}
            </div>
            <div>
              <div className="modal-title">Import complete</div>
              <div className="modal-sub">{name}</div>
            </div>
          </div>
          <button className="modal-close" onClick={close}><Icon name="x" /></button>
        </div>
        <div className="modal-body">
          {/* Summary */}
          <div
            style={{
              padding: 14, borderRadius: 10,
              background: result.written_count > 0
                ? 'rgba(46,184,138,0.10)'
                : 'rgba(240,162,60,0.10)',
              border: `1px solid ${result.written_count > 0
                ? 'rgba(46,184,138,0.35)'
                : 'rgba(240,162,60,0.35)'}`,
              color: result.written_count > 0 ? 'var(--c-pos)' : 'var(--c-crypto)',
              fontSize: 13, lineHeight: 1.6,
            }}
          >
            <div style={{ fontWeight: 600, marginBottom: 4 }}>
              {result.written_count} {result.written_count === 1 ? 'row' : 'rows'} written
            </div>
            {result.date_from && result.date_to && (
              <div style={{ color: 'var(--fg-2)' }}>
                {result.date_from} → {result.date_to}
              </div>
            )}
          </div>

          {/* Skipped */}
          {hasSkipped && (
            <div style={{ marginTop: 10 }}>
              <div style={{ fontSize: 12, color: 'var(--fg-2)', marginBottom: 4 }}>
                {result.skipped_count} {result.skipped_count === 1 ? 'date' : 'dates'} skipped
                {' '}(existing data preserved)
              </div>
              <div
                style={{
                  maxHeight: 80, overflowY: 'auto',
                  fontSize: 11, color: 'var(--fg-3)',
                  fontFamily: 'monospace',
                  background: 'var(--surf-2)', borderRadius: 6, padding: '6px 8px',
                }}
              >
                {result.skipped_dates.slice(0, 20).join(', ')}
                {result.skipped_dates.length > 20 && ` … +${result.skipped_dates.length - 20} more`}
              </div>
            </div>
          )}

          {/* Invalid rows */}
          {hasInvalid && (
            <div style={{ marginTop: 10 }}>
              <div style={{ fontSize: 12, color: 'var(--c-neg)', marginBottom: 4 }}>
                {result.invalid_rows.length} {result.invalid_rows.length === 1 ? 'row' : 'rows'} could not be parsed
              </div>
              <div
                style={{
                  maxHeight: 80, overflowY: 'auto',
                  fontSize: 11, color: 'var(--fg-3)',
                  background: 'var(--surf-2)', borderRadius: 6, padding: '6px 8px',
                }}
              >
                {result.invalid_rows.map(r => (
                  <div key={r.row_num}>Row {r.row_num}: {r.reason}</div>
                ))}
              </div>
            </div>
          )}
        </div>
        <div className="modal-foot">
          <button className="btn btn-primary" onClick={close}>Done</button>
        </div>
      </div>
    )
  }

  // ── form ───────────────────────────────────────────────────────────────
  const canSubmit = !!file && !mut.isPending

  return (
    <div className="modal">
      <div className="modal-head">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div className="platform-abbr" style={{ background: color, color: textColor }}>
            {abbr}
          </div>
          <div>
            <div className="modal-title">Import history</div>
            <div className="modal-sub">{name}{connector.account_label ? ` · ${connector.account_label}` : ''}</div>
          </div>
        </div>
        <button className="modal-close" onClick={close}><Icon name="x" /></button>
      </div>

      <div className="modal-body">
        {/* CSV format hint */}
        <div
          style={{
            padding: '10px 12px', borderRadius: 8,
            background: 'var(--surf-2)',
            border: '1px solid var(--bdr)',
            fontSize: 12, color: 'var(--fg-2)', lineHeight: 1.6, marginBottom: 14,
          }}
        >
          <div style={{ fontWeight: 600, color: 'var(--fg)', marginBottom: 4 }}>
            CSV format
          </div>
          <code style={{ display: 'block', color: 'var(--fg-3)', fontSize: 11 }}>
            date,total_value{'\n'}
            2024-01-01,50000{'\n'}
            2024-01-02,51200.50
          </code>
          <div style={{ marginTop: 6 }}>
            Two columns required: <code>date</code> (YYYY-MM-DD) and <code>total_value</code>.
            Max 5,000 rows · 5 MB.
          </div>
        </div>

        {/* File picker */}
        <div className="field">
          <label className="field-label">CSV file</label>
          <input
            ref={fileRef}
            type="file"
            accept=".csv,text/csv"
            style={{ display: 'none' }}
            onChange={e => setFile(e.target.files?.[0] ?? null)}
          />
          <button
            type="button"
            className="btn btn-ghost"
            style={{ width: '100%', justifyContent: 'center', gap: 8 }}
            onClick={() => fileRef.current?.click()}
          >
            <Icon name="upload" />
            {file ? file.name : 'Choose CSV file…'}
          </button>
          {file && (
            <div style={{ fontSize: 11, color: 'var(--fg-3)', marginTop: 4 }}>
              {(file.size / 1024).toFixed(1)} KB
            </div>
          )}
        </div>

        {/* Currency */}
        <div className="field">
          <label className="field-label">Currency of values in CSV</label>
          <select
            className="select"
            value={currency}
            onChange={e => setCurrency(e.target.value as 'USD' | 'TWD')}
          >
            <option value="USD">USD (US Dollar)</option>
            <option value="TWD">TWD (Taiwan Dollar — auto-converted to USD)</option>
          </select>
        </div>

        {/* Conflict strategy */}
        <div className="field">
          <label className="field-label">If a date already has data</label>
          <select
            className="select"
            value={conflictStrategy}
            onChange={e => setConflictStrategy(e.target.value as 'skip' | 'override')}
          >
            <option value="skip">Skip — keep existing data, import only new dates</option>
            <option value="override">Override — replace existing data for conflicting dates</option>
          </select>
        </div>

        {error && (
          <div
            style={{
              padding: 10, borderRadius: 8,
              background: 'rgba(236,91,126,0.08)',
              border: '1px solid rgba(236,91,126,0.3)',
              color: 'var(--c-neg)', fontSize: 12,
            }}
          >
            {error}
          </div>
        )}
      </div>

      <div className="modal-foot">
        <button className="btn btn-ghost" onClick={close}>Cancel</button>
        <button
          className="btn btn-primary"
          onClick={() => mut.mutate()}
          disabled={!canSubmit}
        >
          Import
        </button>
      </div>
    </div>
  )
}
