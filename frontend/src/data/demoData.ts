// Deterministic seeded LCG random number generator
function makeRng(seed: number): () => number {
  let s = seed >>> 0
  return () => {
    s = (Math.imul(1664525, s) + 1013904223) >>> 0
    return s / 0x100000000
  }
}

// Generate Mon–Fri dates between start and end inclusive
function genDates(start: string, end: string): string[] {
  const dates: string[] = []
  const d = new Date(start + 'T12:00:00Z')
  const e = new Date(end + 'T12:00:00Z')
  while (d <= e) {
    if (d.getUTCDay() !== 0 && d.getUTCDay() !== 6) {
      dates.push(d.toISOString().slice(0, 10))
    }
    d.setUTCDate(d.getUTCDate() + 1)
  }
  return dates
}

// Random walk from startVal → endVal with per-step volatility (abs USD)
function genSeries(n: number, startVal: number, endVal: number, vol: number, rng: () => number): number[] {
  if (n === 0) return []
  if (n === 1) return [startVal]
  const result: number[] = [startVal]
  const drift = (endVal - startVal) / n
  for (let i = 1; i < n - 1; i++) {
    const noise = (rng() - 0.5) * 2 * vol
    result.push(result[i - 1] + drift + noise)
  }
  result.push(endVal)
  return result
}

// ── Generate all series ───────────────────────────────────────────────────────

const rng = makeRng(0xdeadbeef)

export const DEMO_DATES = genDates('2026-01-02', '2026-06-25')
const N = DEMO_DATES.length

const cryptoSeries   = genSeries(N, 22000, 33000, 600,  rng)
const usSeries       = genSeries(N, 21000, 25700, 250,  rng)
const twSeries       = genSeries(N, 7000,  8800,  150,  rng)
const totalSeries    = cryptoSeries.map((v, i) => v + usSeries[i] + twSeries[i])

const sp500Series    = genSeries(N, 5850,  6120,  40,   rng)
const ndxSeries      = genSeries(N, 20800, 22400, 180,  rng)
const soxSeries      = genSeries(N, 5100,  5950,  90,   rng)
const tw0050Series   = genSeries(N, 174,   192,   1.5,  rng)
const btcSeries      = genSeries(N, 48000, 65000, 1500, rng)

// ── Exported demo datasets ────────────────────────────────────────────────────

export const DEMO_META = {
  last_updated: '2026-06-25T00:00:00Z',
  usd_twd_rate: 32.3,
}

const latest = {
  total:    totalSeries[N - 1],
  crypto:   cryptoSeries[N - 1],
  us_stock: usSeries[N - 1],
  tw_stock: twSeries[N - 1],
}

export const DEMO_HISTORY = {
  dates: DEMO_DATES,
  series: {
    total:    totalSeries,
    crypto:   cryptoSeries,
    us_stock: usSeries,
    tw_stock: twSeries,
  },
  latest,
  metrics: {
    total:    { total_return: 0.350, sharpe: 1.42, mdd: -0.087 },
    crypto:   { total_return: 0.500, sharpe: 0.98, mdd: -0.152 },
    us_stock: { total_return: 0.224, sharpe: 1.85, mdd: -0.043 },
    tw_stock: { total_return: 0.257, sharpe: 1.31, mdd: -0.038 },
  },
}

export const DEMO_BENCHMARKS = {
  benchmarks: [
    { ticker: '^GSPC',   label: 'S&P 500',  color: '#a371f7', dates: DEMO_DATES, closes: sp500Series  },
    { ticker: '^NDX',    label: 'NASDAQ100', color: '#58a6ff', dates: DEMO_DATES, closes: ndxSeries   },
    { ticker: '^SOX',    label: '費半',      color: '#e3b341', dates: DEMO_DATES, closes: soxSeries   },
    { ticker: '0050.TW', label: '0050',     color: '#39d353', dates: DEMO_DATES, closes: tw0050Series },
    { ticker: 'BTC-USD', label: 'BTC',     color: '#f0883e', dates: DEMO_DATES, closes: btcSeries    },
  ],
}

export const DEMO_METRICS = {
  total:    { total_return: 0.350, sharpe: 1.42, mdd: -0.087 },
  crypto:   { total_return: 0.500, sharpe: 0.98, mdd: -0.152 },
  us_stock: { total_return: 0.224, sharpe: 1.85, mdd: -0.043 },
  tw_stock: { total_return: 0.257, sharpe: 1.31, mdd: -0.038 },
}

export const DEMO_ALLOCATION = {
  total: latest.total,
  categories: [
    { key: 'crypto',   label: '幣圈', value_usd: latest.crypto,   pct: +(latest.crypto   / latest.total * 100).toFixed(1) },
    { key: 'us_stock', label: '美股', value_usd: latest.us_stock, pct: +(latest.us_stock / latest.total * 100).toFixed(1) },
    { key: 'tw_stock', label: '台股', value_usd: latest.tw_stock, pct: +(latest.tw_stock / latest.total * 100).toFixed(1) },
  ],
}

export const DEMO_DRILL: Record<string, { category: string; label: string; items: { symbol: string; value_usd: number; pct: number }[] }> = {
  crypto: {
    category: 'crypto', label: '幣圈',
    items: [
      { symbol: 'BTC',  value_usd: 18200, pct: 55.2 },
      { symbol: 'ETH',  value_usd: 11200, pct: 34.0 },
      { symbol: 'BNB',  value_usd: 2300,  pct: 7.0  },
      { symbol: 'USDC', value_usd: 1000,  pct: 3.0  },
      { symbol: 'AAVE', value_usd: 300,   pct: 0.9  },
    ],
  },
  us_stock: {
    category: 'us_stock', label: '美股',
    items: [
      { symbol: 'MSFT', value_usd: 7500, pct: 29.2 },
      { symbol: 'SPY',  value_usd: 6672, pct: 26.0 },
      { symbol: 'AAPL', value_usd: 6150, pct: 23.9 },
      { symbol: 'NVDA', value_usd: 3250, pct: 12.6 },
      { symbol: 'AMZN', value_usd: 2100, pct: 8.2  },
    ],
  },
  tw_stock: {
    category: 'tw_stock', label: '台股',
    items: [
      { symbol: '2330', value_usd: 5875, pct: 66.8 },
      { symbol: '2454', value_usd: 1813, pct: 20.6 },
      { symbol: '2317', value_usd: 813,  pct: 9.2  },
    ],
  },
}

export const DEMO_SNAPSHOT = {
  date: DEMO_DATES[N - 1],
  categories: {
    crypto: {
      actual_date: DEMO_DATES[N - 1],
      items: [
        { symbol: 'BTC',  pct: 55.2 },
        { symbol: 'ETH',  pct: 34.0 },
        { symbol: 'BNB',  pct: 7.0  },
        { symbol: 'USDC', pct: 3.0  },
        { symbol: 'AAVE', pct: 0.9  },
      ],
    },
    us_stock: {
      actual_date: DEMO_DATES[N - 1],
      items: [
        { symbol: 'MSFT', pct: 29.2 },
        { symbol: 'SPY',  pct: 26.0 },
        { symbol: 'AAPL', pct: 23.9 },
        { symbol: 'NVDA', pct: 12.6 },
        { symbol: 'AMZN', pct: 8.2  },
      ],
    },
    tw_stock: {
      actual_date: DEMO_DATES[N - 1],
      items: [
        { symbol: '2330', pct: 66.8 },
        { symbol: '2454', pct: 20.6 },
        { symbol: '2317', pct: 9.2  },
      ],
    },
  },
}

export const DEMO_CONNECTORS = [
  {
    id: 'demo-ibkr',
    platform_name: 'ibkr',
    account_key: 'U1234567',
    account_label: 'IBKR 美股',
    status: 'synced',
    last_sync_at: '2026-06-25T06:00:00Z',
    last_error: null,
    last_error_at: null,
    created_at: '2026-01-02T00:00:00Z',
  },
  {
    id: 'demo-yuanta',
    platform_name: 'yuanta',
    account_key: 'demo_yuanta',
    account_label: '元大證券',
    status: 'synced',
    last_sync_at: '2026-06-25T07:00:00Z',
    last_error: null,
    last_error_at: null,
    created_at: '2026-01-02T00:00:00Z',
  },
  {
    id: 'demo-binance',
    platform_name: 'binance',
    account_key: 'demo_binance',
    account_label: '幣安',
    status: 'synced',
    last_sync_at: '2026-06-25T08:00:00Z',
    last_error: null,
    last_error_at: null,
    created_at: '2026-01-02T00:00:00Z',
  },
  {
    id: 'demo-evm',
    platform_name: 'evm_wallet',
    account_key: '0x742d35Cc6634C0532925a3b8D4C2C4e1DB9Cc5e8',
    account_label: 'ETH 錢包',
    status: 'synced',
    last_sync_at: '2026-06-25T08:30:00Z',
    last_error: null,
    last_error_at: null,
    created_at: '2026-01-02T00:00:00Z',
  },
]

export const DEMO_HOLDINGS = {
  summary: {
    total_usd:    latest.total,
    crypto_usd:   latest.crypto,
    us_stock_usd: latest.us_stock,
    tw_stock_usd: latest.tw_stock,
  },
  platforms: [
    {
      name: 'binance', display: 'Binance', abbr: 'BNB',
      color: '#f3ba2f', fg: '#000', category: 'crypto',
      total_usd: 27500,
      sections: [{
        label: 'Spot', total_usd: 27500,
        rows: [
          { symbol: 'BTC', name: 'Bitcoin',  quantity: '0.28', price: '$65,000', value_usd: 18200 },
          { symbol: 'ETH', name: 'Ethereum', quantity: '2.5',  price: '$2,800',  value_usd: 7000  },
          { symbol: 'BNB', name: 'BNB',      quantity: '5',    price: '$460',    value_usd: 2300  },
        ],
      }],
    },
    {
      name: 'evm_wallet', display: 'ETH Wallet', abbr: 'ETH',
      color: '#627eea', fg: '#fff', category: 'crypto',
      total_usd: 5500,
      accounts: [{
        account_key: '0x742d35Cc6634C0532925a3b8D4C2C4e1DB9Cc5e8_ethereum',
        address: '0x742d35Cc6634C0532925a3b8D4C2C4e1DB9Cc5e8',
        chain: 'ethereum',
        label: 'Main Wallet',
        total_usd: 5500,
        sections: [{
          label: 'Tokens', total_usd: 5500,
          rows: [
            { symbol: 'ETH',  name: 'Ethereum', quantity: '1.5',   price: '$2,800', value_usd: 4200 },
            { symbol: 'USDC', name: 'USD Coin', quantity: '1,000', price: '$1.00',  value_usd: 1000 },
            { symbol: 'AAVE', name: 'Aave',     quantity: '2.5',   price: '$120',   value_usd: 300  },
          ],
        }],
      }],
    },
    {
      name: 'ibkr', display: 'Interactive Brokers', abbr: 'IB',
      color: '#c8102e', fg: '#fff', category: 'us_stock',
      total_usd: latest.us_stock,
      sections: [{
        label: 'US Stocks', total_usd: latest.us_stock,
        rows: [
          { symbol: 'MSFT', name: 'Microsoft',        quantity: '20', price: '$375.00', value_usd: 7500 },
          { symbol: 'SPY',  name: 'SPDR S&P 500 ETF', quantity: '12', price: '$556.00', value_usd: 6672 },
          { symbol: 'AAPL', name: 'Apple',            quantity: '30', price: '$205.00', value_usd: 6150 },
          { symbol: 'NVDA', name: 'NVIDIA',           quantity: '20', price: '$162.50', value_usd: 3250 },
          { symbol: 'AMZN', name: 'Amazon',           quantity: '10', price: '$210.00', value_usd: 2100 },
        ],
      }],
    },
    {
      name: 'yuanta', display: '元大證券', abbr: '元大',
      color: '#e31e24', fg: '#fff', category: 'tw_stock',
      total_usd: latest.tw_stock,
      sections: [{
        label: 'TW Stocks', total_usd: latest.tw_stock,
        rows: [
          { symbol: '2330', name: '台積電', quantity: '210', price: 'TWD 940', value_usd: 6169 },
          { symbol: '2454', name: '聯發科', quantity: '100', price: 'TWD 580', value_usd: 1813 },
          { symbol: '2317', name: '鴻海',   quantity: '200', price: 'TWD 135', value_usd: 844  },
        ],
      }],
    },
  ],
}
