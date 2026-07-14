import { useQuery } from '@tanstack/react-query'
import { api } from './client'
import { useAuth } from '../auth/AuthContext'

export interface Entitlement {
  active: boolean
  status: string
  provider: string | null
  current_period_end: string | null
  cancel_at_period_end: boolean
}

export async function getBillingStatus(): Promise<Entitlement> {
  const r = await api.get('/api/billing/status')
  return r.data
}

interface EcpayCheckout {
  action: string
  params: Record<string, string>
}

/** Fetch the ECPay recurring-payment order and form-POST the browser to 綠界 付款頁. */
export async function redirectToEcpayCheckout(): Promise<void> {
  const r = await api.post('/api/billing/checkout')
  const { action, params } = r.data as EcpayCheckout
  const form = document.createElement('form')
  form.method = 'POST'
  form.action = action
  for (const [name, value] of Object.entries(params)) {
    const input = document.createElement('input')
    input.type = 'hidden'
    input.name = name
    input.value = value
    form.appendChild(input)
  }
  document.body.appendChild(form)
  form.submit()
}

/** Terminate future charges; the paid period stays usable until it ends. */
export async function cancelSubscription(): Promise<void> {
  await api.post('/api/billing/cancel')
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
