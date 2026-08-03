/**
 * Source templates shown in the AddSource modal. The `id` field aligns with the
 * backend `platform_name` whenever `implemented` is true; otherwise the template
 * is just a visual placeholder.
 */

export type AuthMethod = 'apikey' | 'address' | 'ibkr' | 'sinopac' | 'fubon' | 'yuanta' | 'email' | 'manual'
export type Category = 'crypto' | 'us' | 'tw' | 'other'

export interface GetApiConfig {
  hasAccountUrl: string
  noAccountUrl: string
  hasAccountTooltip: string
  noAccountTooltip: string
  apiWarning?: string
}

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
  singleInstance?: boolean  // if true, disable add button when user already has this connector
  getApiConfig?: GetApiConfig
  logoUrl?: string  // if set, renders as <img> instead of colored abbr badge
}

export const SOURCE_TEMPLATES: SourceTemplate[] = [
  {
    id: 'binance', name: 'Binance', desc: '加密貨幣交易所', category: 'crypto', auth: 'apikey',
    abbr: 'BNB', color: '#f3ba2f', textColor: '#000', implemented: true, logoUrl: '/logos/binance.png',
    getApiConfig: {
      hasAccountUrl: 'https://www.binance.com/zh-TC/my/settings/api-management',
      noAccountUrl: 'https://www.binance.com/register?ref=XINGYEN',
      hasAccountTooltip: 'API權限請只開啟讀取(唯讀)權限，其餘權限，如：交易，提款等等功能，請勿開啟',
      noAccountTooltip: '走此連結註冊想有現貨20%手續費折抵＆合約10％手續費折抵',
    },
  },
  {
    id: 'okx', name: 'OKX', desc: '加密貨幣交易所', category: 'crypto', auth: 'apikey',
    abbr: 'OKX', color: '#000', textColor: '#fff', implemented: true, logoUrl: '/logos/okx.png',
    getApiConfig: {
      hasAccountUrl: 'https://www.okx.com/zh-hant/account/my-api',
      noAccountUrl: 'https://okx.com/join/99545884',
      hasAccountTooltip: 'API權限請只開啟讀取(唯讀)權限，其餘權限，如：交易，提款等等功能，請勿開啟',
      noAccountTooltip: '完成新手任務，最高100USD獎勵，以官方公告為主',
    },
  },
  {
    id: 'mexc', name: 'MEXC', desc: '加密貨幣交易所', category: 'crypto', auth: 'apikey',
    abbr: 'MEXC', color: '#1972e8', textColor: '#fff', implemented: true, logoUrl: '/logos/mexc.webp',
    getApiConfig: {
      hasAccountUrl: 'https://www.mexc.com/zh-TW/user/openapi',
      noAccountUrl: 'https://promote.mexc.com/r/E7qim6IUA5',
      hasAccountTooltip: 'API權限請只開啟讀取(唯讀)權限並開啟所有範圍，其餘權限，如：交易，提款等等功能，請勿開啟',
      noAccountTooltip: '註冊 MEXC 賬戶，解鎖高達$60 邀請計劃專屬獎勵！可疊加 $10,000 新人福利！',
      apiWarning: 'MEXC API 有90天期限，需自行定期回來更新API KEY',
    },
  },
  {
    id: 'bybit', name: 'Bybit', desc: '加密貨幣交易所', category: 'crypto', auth: 'apikey',
    abbr: 'BYBT', color: '#f7a600', textColor: '#000', implemented: true, logoUrl: '/logos/bybit.png',
    getApiConfig: {
      hasAccountUrl: 'https://www.bybit.com/app/user/api-management',
      noAccountUrl: 'https://www.bybit.com/invite?ref=WPYNEE&medium=referral&utm_campaign=evergreen',
      hasAccountTooltip: 'API權限請只開啟讀取(唯讀)權限並開啟所有範圍，其餘權限，如：交易，提款等等功能，請勿開啟',
      noAccountTooltip: '註冊 Bybit 賬戶，解鎖 Bybit 推薦計畫專屬獎勵！更有高達 6,135 USDT 獎勵等您領取',
    },
  },
  {
    id: 'pionex', name: '派網 Pionex', desc: '加密貨幣交易所', category: 'crypto', auth: 'apikey',
    abbr: 'PIX', color: '#f15a28', textColor: '#fff', implemented: true,
    logoUrl: '/logos/pionex.png',
    getApiConfig: {
      hasAccountUrl: 'https://www.pionex.com/zh-TW/my-account/api',
      noAccountUrl: 'https://www.pionex.com/zh-TW/signUp?r=0X3pTSpQsA2',
      hasAccountTooltip: 'API 權限請只勾選讀取(唯讀)相關權限，請勿勾選交易或提款等功能',
      noAccountTooltip: '走此連結註冊可獲得合約交易15%手續費及現貨10%手續費反饋',
    },
  },
  { id: 'coinbase', name: 'Coinbase',          desc: '加密貨幣交易所',              category: 'crypto', auth: 'apikey',  abbr: 'CB',   color: '#0052ff', textColor: '#fff', implemented: false, comingSoon: '即將推出' },
  { id: 'evm_wallet', name: 'EVM 錢包',        desc: 'Ethereum / Polygon / BSC 錢包', category: 'crypto', auth: 'address', abbr: 'ETH',  color: '#627eea', textColor: '#fff', implemented: true, logoUrl: '/logos/evm.png' },
  { id: 'sol_wallet', name: 'Solana 錢包',     desc: 'SOL 錢包（唯讀）',            category: 'crypto', auth: 'address', abbr: 'SOL',  color: '#9945ff', textColor: '#fff', implemented: true, logoUrl: '/logos/solana.jpeg' },
  { id: 'sui_wallet', name: 'SUI 錢包',        desc: 'SUI 錢包（唯讀）',            category: 'crypto', auth: 'address', abbr: 'SUI',  color: '#6fbcf0', textColor: '#000', implemented: true, logoUrl: '/logos/sui.jpeg' },
  { id: 'hyperliquid', name: 'Hyperliquid',    desc: '永續合約 + 現貨（唯讀）',      category: 'crypto', auth: 'address', abbr: 'HL',   color: '#97fce4', textColor: '#000', implemented: true },
  { id: 'ibkr',     name: 'Interactive Brokers', desc: '美股券商 · Flex Web',       category: 'us',     auth: 'ibkr',    abbr: 'IBKR', color: '#cc0000', textColor: '#fff', implemented: true, logoUrl: '/logos/ibkr.png' },
  { id: 'schwab',   name: 'Charles Schwab',    desc: '美股券商',                    category: 'us',     auth: 'manual',  abbr: 'SCHW', color: '#00a0df', textColor: '#fff', implemented: false, comingSoon: '即將推出' },
  { id: 'yuanta',   name: '元大證券',           desc: '台灣券商 · Gmail PDF',        category: 'tw',     auth: 'yuanta',  abbr: 'YT',   color: '#004b99', textColor: '#fff', implemented: true, singleInstance: true },
  { id: 'sinopac',  name: '永豐證券',           desc: '台灣券商 · Shioaji API',      category: 'tw',   auth: 'sinopac', abbr: '永',   color: '#003D82', textColor: '#fff', implemented: true, logoUrl: '/logos/sinopac.jpg' },
  { id: 'fubon',    name: '富邦證券',           desc: '台灣券商 · Neo API',          category: 'tw',     auth: 'fubon',   abbr: 'FB',   color: '#0a5e3e', textColor: '#fff', implemented: true, logoUrl: '/logos/fubon.png' },
  { id: 'manual',   name: '手動輸入',           desc: '不動產、現金、自訂資產',       category: 'other',  auth: 'manual',  abbr: '+',    color: '#3a3a44', textColor: '#fff', implemented: false, comingSoon: 'v2 推出' },
]

export const CATEGORY_LABEL: Record<Category | 'all', string> = {
  all: '全部',
  crypto: '加密貨幣',
  us: '美股',
  tw: '台股',
  other: '其他',
}

export function getTemplate(id: string): SourceTemplate | undefined {
  return SOURCE_TEMPLATES.find(t => t.id === id)
}
