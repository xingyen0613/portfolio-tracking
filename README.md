# Portfolio Tracking

個人資產追蹤系統，整合 CEX（Binance、OKX）與 SUI 鏈上錢包資料，每日快照存入 SQLite。

## 資料來源

| 平台 | 資料類型 | API |
|------|---------|-----|
| Binance | Spot + Earn（Flexible/Locked） | ccxt |
| OKX | Spot + Savings | ccxt |
| SUI Wallet | Token 餘額 + DeFi 倉位 | BlockVision v2 |

## 執行

```bash
# 所有平台
uv run python -m app.jobs.run_batch

# 單一平台
uv run python -m app.jobs.run_batch --platform sui_wallet
```

## 定價說明與已知近似值

### SUI Liquid Staking Token（LST）

以下 token 目前以對應底層資產價格計算，實際價值可能因質押收益略有差異：

| Token | 計價依據 | 說明 |
|-------|---------|------|
| vSUI | SUI 價格 | Volo 質押 SUI |
| xSUI | SUI 價格 | Aftermath 質押 SUI |

### SUI Token 驗證規則

只有 BlockVision 標記 `verified: true` 且 `scam: false` 的 token 才會被記錄。
未驗證或被標記為詐騙的 token 一律過濾，不計入資產總值。

### DeFi 倉位

DeFi 倉位（借貸、LP、質押）若 BlockVision 無 USD 報價，由 Binance/OKX 市場價補充。
無法取得報價的倉位僅記錄數量，value 留空。
