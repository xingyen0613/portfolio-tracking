import { useQuery } from '@tanstack/react-query'
import { api } from './client'
import { useAuth } from '../auth/AuthContext'

export interface Entitlement {
  active: boolean
  status: string
  provider: string | null
  current_period_end: string | null
}

export async function getBillingStatus(): Promise<Entitlement> {
  const r = await api.get('/api/billing/status')
  return r.data
}

/** Current user's subscription entitlement. Only fetched when logged in. */
export function useEntitlement() {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['billing-status'],
    queryFn: getBillingStatus,
    enabled: !!token,
    staleTime: 60_000,
  })
}
