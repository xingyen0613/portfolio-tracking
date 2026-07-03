import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { useDemo } from './DemoContext'
import { DEMO_META } from '../data/demoData'

interface MetaData {
  last_updated: string | null
  usd_twd_rate: number
}

export interface CurrencyCtx {
  currency: 'USD' | 'TWD'
  toggle: () => void
  rate: number
  lastUpdated: string | null
  convert: (usd: number) => number
  fmt: (usd: number) => string
}

const CurrencyContext = createContext<CurrencyCtx | null>(null)

export function CurrencyProvider({ children }: { children: ReactNode }) {
  const [currency, setCurrency] = useState<'USD' | 'TWD'>('USD')
  const { isDemo } = useDemo()

  const { data: meta } = useQuery<MetaData>({
    queryKey: ['portfolio/meta'],
    queryFn: () => api.get('/api/portfolio/meta').then(r => r.data),
    staleTime: 5 * 60 * 1000,
    enabled: !isDemo,
    initialData: isDemo ? DEMO_META : undefined,
  })

  const rate = meta?.usd_twd_rate ?? 1

  const toggle = useCallback(() => setCurrency(c => c === 'USD' ? 'TWD' : 'USD'), [])

  const convert = useCallback(
    (usd: number) => currency === 'TWD' ? usd * rate : usd,
    [currency, rate],
  )

  const fmt = useCallback(
    (usd: number) => {
      const v = convert(usd)
      if (!isFinite(v)) return '—'
      const abs = Math.abs(v)
      const sign = v < 0 ? '-' : ''
      if (currency === 'TWD') {
        if (abs >= 1_000_000) return `${sign}NT$${(abs / 1_000_000).toFixed(2)}M`
        if (abs >= 1_000)     return `${sign}NT$${(abs / 1_000).toFixed(1)}k`
        return `${sign}NT$${abs.toFixed(0)}`
      }
      if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(2)}M`
      if (abs >= 1_000)     return `${sign}$${(abs / 1_000).toFixed(1)}k`
      return `${sign}$${abs.toFixed(0)}`
    },
    [convert, currency],
  )

  return (
    <CurrencyContext.Provider value={{
      currency, toggle, rate, lastUpdated: meta?.last_updated ?? null, convert, fmt,
    }}>
      {children}
    </CurrencyContext.Provider>
  )
}

export function useCurrency(): CurrencyCtx {
  const ctx = useContext(CurrencyContext)
  if (!ctx) throw new Error('useCurrency must be used within CurrencyProvider')
  return ctx
}
