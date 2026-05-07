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

export async function createConnector(
  payload: ConnectorCreatePayload,
): Promise<ConnectorCreateResponse> {
  const r = await api.post('/api/connectors', payload)
  return r.data
}

export async function deleteConnector(id: string): Promise<void> {
  await api.delete(`/api/connectors/${id}`)
}

export async function refreshConnector(id: string): Promise<ConnectorCreateResponse> {
  const r = await api.post(`/api/connectors/${id}/refresh`)
  return r.data
}
