import { useCallback, useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import axios from 'axios'
import { Icon } from '../Icon'
import {
  type Connector,
  type ImportHistoryResult,
  importHistoricalData,
  previewHistoricalImport,
} from '../../api/connectors'
import { getTemplate } from '../../data/sourceTemplates'

interface Props {
  connector: Connector
  close: () => void
  onImportDone: (result: ImportHistoryResult) => void
}

type Phase = 'form' | 'checking' | 'conflict' | 'uploading' | 'result'

export default function ImportHistoryModal({ connector, close, onImportDone }: Props) {
  const t = getTemplate(connector.platform_name)
  const abbr = t?.abbr ?? connector.platform_name.slice(0, 3).toUpperCase()
  const name = t?.name ?? connector.platform_name
  const color = t?.color ?? '#3a3a44'
  const textColor = t?.textColor ?? '#fff'

  const [file, setFile] = useState<File | null>(null)
  const [currency, setCurrency] = useState<'USD' | 'TWD'>('USD')
  const [phase, setPhase] = useState<Phase>('form')
  const [conflictingDates, setConflictingDates] = useState<string[]>([])
  const [result, setResult] = useState<ImportHistoryResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isDragging, setIsDragging] = useState(false)

  const handleFile = useCallback((f: File | undefined | null) => {
    if (f?.name.toLowerCase().endsWith('.csv')) setFile(f)
  }, [])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    handleFile(e.dataTransfer.files[0])
  }, [handleFile])

  function handleApiError(err: unknown) {
    setPhase('form')
    if (axios.isAxiosError(err)) {
      const detail = err.response?.data?.detail
      setError(typeof detail === 'string' ? detail : err.message)
    } else {
      setError(err instanceof Error ? err.message : 'Upload failed')
    }
  }

  // Step 2: actual import (defined first so doImport can reference it)
  const importMut = useMutation({
    mutationFn: (strategy: 'skip' | 'override') =>
      importHistoricalData(connector.id, file!, currency, strategy),
    onMutate: () => {
      setPhase('uploading')
      setError(null)
    },
  })

  // Keep latest onImportDone in a ref so the mutate() callback always calls the current version
  const onImportDoneRef = useRef(onImportDone)
  onImportDoneRef.current = onImportDone

  // mutate() argument callbacks fire even after component unmount (unlike useMutation option callbacks)
  const doImport = useCallback((strategy: 'skip' | 'override') => {
    importMut.mutate(strategy, {
      onSuccess: (data) => {
        onImportDoneRef.current(data)
        setResult(data)
        setPhase('result')
      },
      onError: handleApiError,
    })
  }, [importMut]) // eslint-disable-line react-hooks/exhaustive-deps

  // Step 1: dry-run — detect conflicts
  const checkMut = useMutation({
    mutationFn: () => previewHistoricalImport(connector.id, file!, currency),
    onMutate: () => {
      setPhase('checking')
      setError(null)
    },
    onSuccess: (data) => {
      if (data.conflicting_dates.length === 0) {
        doImport('skip')
      } else {
        setConflictingDates(data.conflicting_dates)
        setPhase('conflict')
      }
    },
    onError: handleApiError,
  })

  // ── checking / uploading ────────────────────────────────────────────────
  if (phase === 'checking' || phase === 'uploading') {
    const msg = phase === 'checking'
      ? 'Checking for conflicts…'
      : 'Uploading and processing your CSV. This may take a few seconds for large files.'
    return (
      <div className="modal">
        <div className="modal-head">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div className="platform-abbr" style={{ background: color, color: textColor }}>{abbr}</div>
            <div className="modal-title">{phase === 'checking' ? 'Checking…' : 'Importing history…'}</div>
          </div>
        </div>
        <div className="modal-body">
          <div style={{
            padding: 14, borderRadius: 10,
            background: 'rgba(240,162,60,0.10)',
            border: '1px solid rgba(240,162,60,0.35)',
            color: 'var(--c-crypto)', fontSize: 13, lineHeight: 1.55,
          }}>
            <div>{msg}</div>
            {phase === 'checking' && (
              <div style={{ marginTop: 6, fontSize: 12, color: 'var(--fg-3)' }}>
                Please don't close this window while checking.
              </div>
            )}
          </div>
        </div>
      </div>
    )
  }

  // ── conflict ────────────────────────────────────────────────────────────
  if (phase === 'conflict') {
    return (
      <div className="modal">
        <div className="modal-head">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div className="platform-abbr" style={{ background: color, color: textColor }}>{abbr}</div>
            <div>
              <div className="modal-title">Duplicate dates found</div>
              <div className="modal-sub">{name}</div>
            </div>
          </div>
        </div>
        <div className="modal-body">
          <div style={{
            padding: 12, borderRadius: 8,
            background: 'rgba(240,162,60,0.10)',
            border: '1px solid rgba(240,162,60,0.35)',
            color: 'var(--c-crypto)', fontSize: 13, marginBottom: 12,
          }}>
            {conflictingDates.length} {conflictingDates.length === 1 ? 'date' : 'dates'} in your CSV already have data.
            How would you like to handle them?
          </div>
          <div
            style={{
              maxHeight: 100, overflowY: 'auto',
              fontSize: 11, color: 'var(--fg-3)',
              fontFamily: 'monospace',
              background: 'var(--surf-2)', borderRadius: 6, padding: '6px 8px', marginBottom: 14,
            }}
          >
            {conflictingDates.slice(0, 30).join(', ')}
            {conflictingDates.length > 30 && ` … +${conflictingDates.length - 30} more`}
          </div>
        </div>
        <div className="modal-foot">
          <button className="btn btn-ghost" onClick={close}>Cancel</button>
          <button
            className="btn btn-ghost"
            onClick={() => doImport('skip')}
          >
            Skip duplicates
          </button>
          <button
            className="btn btn-primary"
            onClick={() => doImport('override')}
          >
            Override existing
          </button>
        </div>
      </div>
    )
  }

  // ── result ──────────────────────────────────────────────────────────────
  if (phase === 'result' && result) {
    const hasSkipped = result.skipped_count > 0
    const hasInvalid = result.invalid_rows.length > 0
    return (
      <div className="modal">
        <div className="modal-head">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div className="platform-abbr" style={{ background: color, color: textColor }}>{abbr}</div>
            <div>
              <div className="modal-title">Import complete</div>
              <div className="modal-sub">{name}</div>
            </div>
          </div>
          <button className="modal-close" onClick={close}><Icon name="x" /></button>
        </div>
        <div className="modal-body">
          <div style={{
            padding: 14, borderRadius: 10,
            background: result.written_count > 0 ? 'rgba(46,184,138,0.10)' : 'rgba(240,162,60,0.10)',
            border: `1px solid ${result.written_count > 0 ? 'rgba(46,184,138,0.35)' : 'rgba(240,162,60,0.35)'}`,
            color: result.written_count > 0 ? 'var(--c-pos)' : 'var(--c-crypto)',
            fontSize: 13, lineHeight: 1.6,
          }}>
            <div style={{ fontWeight: 600, marginBottom: 4 }}>
              {result.written_count} {result.written_count === 1 ? 'row' : 'rows'} written
            </div>
            {result.date_from && result.date_to && (
              <div style={{ color: 'var(--fg-2)' }}>{result.date_from} → {result.date_to}</div>
            )}
          </div>

          {hasSkipped && (
            <div style={{ marginTop: 10 }}>
              <div style={{ fontSize: 12, color: 'var(--fg-2)', marginBottom: 4 }}>
                {result.skipped_count} {result.skipped_count === 1 ? 'date' : 'dates'} skipped (existing data preserved)
              </div>
              <div style={{
                maxHeight: 80, overflowY: 'auto',
                fontSize: 11, color: 'var(--fg-3)',
                fontFamily: 'monospace',
                background: 'var(--surf-2)', borderRadius: 6, padding: '6px 8px',
              }}>
                {result.skipped_dates.slice(0, 20).join(', ')}
                {result.skipped_dates.length > 20 && ` … +${result.skipped_dates.length - 20} more`}
              </div>
            </div>
          )}

          {hasInvalid && (
            <div style={{ marginTop: 10 }}>
              <div style={{ fontSize: 12, color: 'var(--c-neg)', marginBottom: 4 }}>
                {result.invalid_rows.length} {result.invalid_rows.length === 1 ? 'row' : 'rows'} could not be parsed
              </div>
              <div style={{
                maxHeight: 80, overflowY: 'auto',
                fontSize: 11, color: 'var(--fg-3)',
                background: 'var(--surf-2)', borderRadius: 6, padding: '6px 8px',
              }}>
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

  // ── form ────────────────────────────────────────────────────────────────
  const canSubmit = !!file && !checkMut.isPending && !importMut.isPending

  return (
    <div className="modal">
      <div className="modal-head">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div className="platform-abbr" style={{ background: color, color: textColor }}>{abbr}</div>
          <div>
            <div className="modal-title">Import history</div>
            <div className="modal-sub">{name}{connector.account_label ? ` · ${connector.account_label}` : ''}</div>
          </div>
        </div>
        <button className="modal-close" onClick={close}><Icon name="x" /></button>
      </div>

      <div className="modal-body">
        {/* CSV format hint */}
        <div style={{
          padding: '10px 12px', borderRadius: 8,
          background: 'var(--surf-2)',
          border: '1px solid var(--bdr)',
          fontSize: 12, color: 'var(--fg-2)', lineHeight: 1.6, marginBottom: 14,
        }}>
          <div style={{ fontWeight: 600, color: 'var(--fg)', marginBottom: 4 }}>CSV format</div>
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

        {/* File drop zone — input overlay covers the zone so any click opens file dialog */}
        <div className="field">
          <label className="field-label">CSV file</label>
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
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
              cursor: 'pointer',
              transition: 'border-color 0.15s, background 0.15s',
            }}
          >
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={e => handleFile(e.target.files?.[0])}
              style={{
                position: 'absolute',
                inset: 0,
                opacity: 0,
                cursor: 'pointer',
                width: '100%',
                height: '100%',
              }}
            />
            <Icon name="upload" />
            <span style={{ fontSize: 13, color: file ? 'var(--fg)' : 'var(--fg-2)', pointerEvents: 'none' }}>
              {file ? file.name : 'Drop CSV here or click to browse'}
            </span>
            {file && (
              <span style={{ fontSize: 11, color: 'var(--fg-3)', pointerEvents: 'none' }}>
                {(file.size / 1024).toFixed(1)} KB
              </span>
            )}
          </div>
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

        {error && (
          <div style={{
            padding: 10, borderRadius: 8,
            background: 'rgba(236,91,126,0.08)',
            border: '1px solid rgba(236,91,126,0.3)',
            color: 'var(--c-neg)', fontSize: 12,
          }}>
            {error}
          </div>
        )}
      </div>

      <div className="modal-foot">
        <button className="btn btn-ghost" onClick={close}>Cancel</button>
        <button
          className="btn btn-primary"
          onClick={() => checkMut.mutate()}
          disabled={!canSubmit}
        >
          Import
        </button>
      </div>
    </div>
  )
}
