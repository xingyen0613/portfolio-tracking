import { api } from './client'

export interface Connector {
  id: string
  platform_name: string
  account_key: string
  account_label: string | null
  status: string
  last_sync_at: string | null
  last_error: string | null
  last_error_at: string | null
  created_at: string | null
}

export interface ConnectorCreatePayload {
  platform_name: string
  account_label: string
  credentials: Record<string, unknown>
}

export interface ConnectorCreateResponse {
  connector: Connector
  fetch_status: 'success' | 'partial' | 'failed'
  fetch_error: string | null
  batch_id: string | null
}

export async function listConnectors(): Promise<Connector[]> {
  const r = await api.get('/api/connectors')
  return r.data
}

// First-sync runs synchronously inside this POST (run_batch). Some platforms
// (binance multi-subaccount, OKX, IBKR Flex queue) can take well over 10s,
// so we override the client default timeout for create + refresh.
const SYNC_TIMEOUT_MS = 180000

export async function createConnector(
  payload: ConnectorCreatePayload,
): Promise<ConnectorCreateResponse> {
  const r = await api.post('/api/connectors', payload, { timeout: SYNC_TIMEOUT_MS })
  return r.data
}

export async function deleteConnector(id: string): Promise<void> {
  await api.delete(`/api/connectors/${id}`)
}

export async function refreshConnector(id: string): Promise<ConnectorCreateResponse> {
  const r = await api.post(`/api/connectors/${id}/refresh`, undefined, {
    timeout: SYNC_TIMEOUT_MS,
  })
  return r.data
}

export interface ImportPreviewResult {
  dry_run: true
  total_parsed: number
  conflicting_dates: string[]
  invalid_rows: { row_num: number; reason: string }[]
}

export async function previewHistoricalImport(
  connectorId: string,
  file: File,
  currency: 'USD' | 'TWD',
): Promise<ImportPreviewResult> {
  const form = new FormData()
  form.append('file', file)
  form.append('currency', currency)
  form.append('dry_run', 'true')
  const r = await api.post(`/api/connectors/${connectorId}/historical-import`, form)
  return r.data
}

export interface ImportHistoryResult {
  import_id: string
  written_count: number
  skipped_count: number
  date_from: string | null
  date_to: string | null
  invalid_rows: { row_num: number; reason: string }[]
  skipped_dates: string[]
}

export async function importHistoricalData(
  connectorId: string,
  file: File,
  currency: 'USD' | 'TWD',
  conflictStrategy: 'skip' | 'override',
): Promise<ImportHistoryResult> {
  const form = new FormData()
  form.append('file', file)
  form.append('currency', currency)
  form.append('conflict_strategy', conflictStrategy)
  const r = await api.post(`/api/connectors/${connectorId}/historical-import`, form)
  return r.data
}

export async function initiateYuantaOAuth(pdfPassword: string): Promise<{ authorize_url: string }> {
  const r = await api.post('/api/auth/yuanta/gmail/authorize', { pdf_password: pdfPassword })
  return r.data
}
