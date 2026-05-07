/**
 * Source templates shown in the AddSource modal. The `id` field aligns with the
 * backend `platform_name` whenever `implemented` is true; otherwise the template
 * is just a visual placeholder.
 */

export type AuthMethod = 'apikey' | 'address' | 'ibkr' | 'email' | 'manual'
export type Category = 'crypto' | 'us' | 'tw' | 'other'

export interface SourceTemplate {
  id: string
  name: string
  desc: string
  category: Category
  auth: AuthMethod
  abbr: string
  color: string
  textColor: string
  implemented: boolean
  comingSoon?: string
}

export const SOURCE_TEMPLATES: SourceTemplate[] = [
  { id: 'binance',  name: 'Binance',           desc: 'Crypto exchange',           category: 'crypto', auth: 'apikey',  abbr: 'BNB',  color: '#f3ba2f', textColor: '#000', implemented: true },
  { id: 'okx',      name: 'OKX',               desc: 'Crypto exchange',           category: 'crypto', auth: 'apikey',  abbr: 'OKX',  color: '#000',    textColor: '#fff', implemented: true },
  { id: 'mexc',     name: 'MEXC',              desc: 'Crypto exchange',           category: 'crypto', auth: 'apikey',  abbr: 'MEXC', color: '#1972e8', textColor: '#fff', implemented: true },
  { id: 'bybit',    name: 'Bybit',             desc: 'Crypto exchange',           category: 'crypto', auth: 'apikey',  abbr: 'BYBT', color: '#f7a600', textColor: '#000', implemented: true },
  { id: 'coinbase', name: 'Coinbase',          desc: 'Crypto exchange',           category: 'crypto', auth: 'apikey',  abbr: 'CB',   color: '#0052ff', textColor: '#fff', implemented: false, comingSoon: 'Coming soon' },
  { id: 'evm_wallet', name: 'EVM Wallet',      desc: 'Ethereum / Polygon / BSC',  category: 'crypto', auth: 'address', abbr: 'ETH',  color: '#627eea', textColor: '#fff', implemented: true },
  { id: 'sol_wallet', name: 'Solana Wallet',   desc: 'SOL wallet (read-only)',    category: 'crypto', auth: 'address', abbr: 'SOL',  color: '#9945ff', textColor: '#fff', implemented: true },
  { id: 'ibkr',     name: 'Interactive Brokers', desc: 'US broker · Flex Web',    category: 'us',     auth: 'ibkr',    abbr: 'IBKR', color: '#cc0000', textColor: '#fff', implemented: true },
  { id: 'schwab',   name: 'Charles Schwab',    desc: 'US broker',                 category: 'us',     auth: 'manual',  abbr: 'SCHW', color: '#00a0df', textColor: '#fff', implemented: false, comingSoon: 'Coming soon' },
  { id: 'yuanta',   name: '元大證券',           desc: 'Taiwan broker · Gmail PDF', category: 'tw',     auth: 'email',   abbr: 'YT',   color: '#004b99', textColor: '#fff', implemented: false, comingSoon: 'Owner-only for now' },
  { id: 'fubon',    name: '富邦證券',           desc: 'Taiwan broker · Gmail PDF', category: 'tw',     auth: 'email',   abbr: 'FB',   color: '#0a5e3e', textColor: '#fff', implemented: false, comingSoon: 'Coming soon' },
  { id: 'manual',   name: 'Manual Entry',      desc: 'Real estate, cash, custom', category: 'other',  auth: 'manual',  abbr: '+',    color: '#3a3a44', textColor: '#fff', implemented: false, comingSoon: 'Coming in v2' },
]

export const CATEGORY_LABEL: Record<Category | 'all', string> = {
  all: 'All',
  crypto: 'Crypto',
  us: 'US Stocks',
  tw: 'TW Stocks',
  other: 'Other',
}

export function getTemplate(id: string): SourceTemplate | undefined {
  return SOURCE_TEMPLATES.find(t => t.id === id)
}
