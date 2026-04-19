# Ubiquitous Language

## Data Pipeline

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Batch** | A single scheduled run that triggers data fetching across all enabled platforms, producing a group of related snapshots | Job, run, cycle |
| **Source Run** | One platform-account's fetch attempt within a Batch, tracking its success/failure status independently | Task, fetch job |
| **Raw Payload** | The immutable, unmodified API response stored as a file — the original evidence of what a platform returned | Raw data, response, dump |
| **Connector** | A module responsible for authenticating, fetching, and ingesting data from one specific platform | Adapter, plugin, integration, client |
| **Ingest** | The process of saving a Raw Payload and recording its metadata — does not transform data | Import, load, ETL |
| **Normalize** | The process of transforming a Raw Payload into structured Normalized Holdings using a versioned parser | Parse, transform, process |
| **Parser** | The versioned logic that reads a Raw Payload and outputs Normalized Holdings — can be re-run against historical raw data | Transformer, converter |

## Data Model

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Platform** | A financial service provider where assets are held (e.g. Binance, OKX, FirstTrade) | Exchange, broker, provider, source |
| **Account** | A distinct account under a Platform, identified by credentials — one Platform can have multiple Accounts | Wallet, portfolio, sub-account |
| **Normalized Holding** | A single asset position within an Account, expressed in the platform's original currency and symbol | Position, balance, holding |
| **Account Snapshot** | A point-in-time record of all Normalized Holdings under one Account, plus the account-level summary | Daily record, balance sheet |
| **Portfolio Snapshot** | A point-in-time aggregate across all Account Snapshots in a single Batch | Total snapshot, global snapshot |

## Asset Identification

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Platform Symbol** | The asset ticker as the platform reports it (e.g. "BTC", "0050") — preserved as-is, not mapped | Ticker, code, symbol |
| **Asset Type** | A minimal classification of an asset: cash, stock, ETF, crypto, stablecoin, wallet_token, unknown | Category, class |
| **Original Currency** | The currency in which the platform reports price and value — no cross-currency conversion in this layer | Base currency, denomination |

## On-chain / Wallet

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Wallet Address** | A blockchain address that holds assets on-chain — one Platform (e.g. SUI) can have multiple Wallet Addresses, each mapped to an Account | Address, wallet, public key |
| **DeFi Position** | An asset deployed into a DeFi protocol (lending, staking, LP) — distinct from a simple token balance | DeFi balance, protocol asset |
| **Protocol** | A specific DeFi application on-chain (e.g. Cetus, Navi, Suilend) from which DeFi Positions are fetched | DApp, contract, pool |
| **Token Balance** | The quantity of a specific coin/token held directly in a Wallet Address, not deployed in any Protocol | Coin balance, native balance |

## Pipeline Layers (within a Connector)

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Auth** | The layer that reads secrets, builds API clients, and handles signing/tokens | Login, session, credentials |
| **Fetch** | The layer that calls platform APIs and returns raw responses — no persistence logic | Request, call, pull |
| **Ingest** | The layer that persists Raw Payloads, records metadata, and performs minimal validation | Store, save, write |

## Daily Reconstruction (元大 月中持倉反推)

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Backward Reconstruction** | The process of deriving daily positions for a Statement Period by starting from the month-end Position Anchor and reversing each transaction backward to the first day | 順推, forward reconstruction, 回推 (use Backward Reconstruction) |
| **Position Anchor** | The month-end `total_shares` per symbol plus `margin_balance`, extracted from a Parsed Statement — the authoritative starting point for Backward Reconstruction | 基準點, anchor, 月底持倉 |
| **Total Shares** | The combined share count of a symbol across all holding types (庫存 + 擔保品) on a given date — the daily-layer representation that does not distinguish owned from pledged | 庫存股數, holdings, 持倉 (in daily context only; month-end layer still uses Stock Holding + Pledged Collateral separately) |
| **Daily Holding** | A single day's reconstructed position record containing Total Shares per symbol and Margin Balance, derived via Backward Reconstruction from one E-Statement | 日重建持倉, daily snapshot, daily record |
| **Cross-Check** | A validation step comparing a month's backward-reconstructed opening position (the implicit Day 0) against the previous month's Position Anchor; a mismatch signals missing transactions or unrecorded corporate actions | 對帳驗證, sanity check, 跨月驗證 |
| **Derived Data** | Data computed from Raw Payloads (e.g., `daily_holdings.json` computed from `parsed.json`) — stored under `data/derived/`, not `data/raw/` | processed data, computed data, 二次資料 |

## Broker Statements (元大 / Firstrade etc.)

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **E-Statement** | A monthly encrypted PDF report from a broker (e.g. 元大電子對帳單), summarizing positions and finances for a Statement Period | 對帳單, monthly report, statement |
| **Statement Period** | The month an E-Statement covers, identified by `YYYY-MM` — distinct from a daily snapshot date | Reporting month, billing cycle |
| **Stock Holding** | A single equity position from an E-Statement (代號, 名稱, 庫存股數, 取得成本, 市值) — the broker-statement equivalent of a Normalized Holding | 個股部位, 股票部位, position |
| **Total Asset** | The broker-reported gross asset value for a Statement Period (資產總額) — before subtracting margin debt | 總資產, gross asset |
| **Margin Debt** | The broker-reported borrowed amount tied to margin/credit accounts (借貸金額) — subtracted from Total Asset to derive Net Asset | 融資餘額, debit balance, 借款 |
| **Net Asset** | The broker-reported net equity value for a Statement Period (淨資產) — Total Asset minus Margin Debt | 淨值, 淨資產, equity |
| **Parsed Statement** | A structured JSON output (`parsed.json`) of a single E-Statement, holding `meta` / `summary` / `holdings` — a PoC-stage intermediate, not yet a DB entity | parsed.json, extracted data |
| **PoC Workspace** | An isolated staging area under `data/raw/yuanta_poc/` for E-Statement experiments, separated from the main Raw Payload pipeline | sandbox, scratch dir, test folder |

## Relationships

- A **Batch** contains one or more **Source Runs**, one per enabled **Platform**-**Account** pair
- A **Source Run** produces one or more **Raw Payloads** (each stored as an immutable file) — e.g. one for tokens, one per DeFi Protocol
- A **Raw Payload** is processed by a **Parser** to produce one or more **Normalized Holdings**
- All **Normalized Holdings** from a single **Source Run** form one **Account Snapshot**
- All **Account Snapshots** within a **Batch** can be aggregated into a **Portfolio Snapshot**
- A **Connector** encapsulates the **Auth** / **Fetch** / **Ingest** layers for one **Platform**
- An **E-Statement** is a broker-specific Raw Payload variant — monthly cadence (vs daily API), arrives as encrypted PDF (vs JSON)
- One **E-Statement** covers one **Statement Period** and produces one **Parsed Statement** containing many **Stock Holdings** plus a single **Total Asset** / **Margin Debt** / **Net Asset** triple
- A **Parsed Statement** lives in the **PoC Workspace** during validation; once schema is stable it will become a Raw Payload + Normalized Holdings entry in the main pipeline
- One **Parsed Statement** provides one **Position Anchor** (month-end) and a list of transactions used by **Backward Reconstruction**
- **Backward Reconstruction** applied to one **Parsed Statement** produces one set of **Daily Holdings** (one per calendar day in the Statement Period), stored as **Derived Data**
- A **Daily Holding** uses **Total Shares** (combined owned + pledged) rather than the split representation used in a **Stock Holding** / **Pledged Collateral**
- **Cross-Check** compares the implicit Day 0 from one month's **Backward Reconstruction** with the **Position Anchor** of the preceding month's **Parsed Statement**

## Example dialogues

> **Dev:** "The Binance **Source Run** failed last night but OKX succeeded. What happens to the **Batch**?"
>
> **Domain expert:** "The **Batch** is marked as partial success. The OKX **Account Snapshot** is written normally. The failed **Source Run** records the error, but doesn't block other platforms."
>
> **Dev:** "Can I re-run just the Binance part today?"
>
> **Domain expert:** "Yes. A new **Source Run** is created under the same or a new **Batch**. The new **Raw Payload** is stored separately — we never overwrite the old one. The **Account Snapshot** uses the latest successful **Source Run's** normalized result."
>
> **Dev:** "What if I update the **Parser** and want to reprocess yesterday's data?"
>
> **Domain expert:** "Read the original **Raw Payload** file, run the new **Parser** version against it, and produce new **Normalized Holdings**. The **Raw Payload** itself is never modified — it's immutable evidence."

> **Dev:** "How does an 元大 **E-Statement** fit into the pipeline? It's monthly, not daily."
>
> **Domain expert:** "During PoC, it doesn't fit — that's why we use the **PoC Workspace**. We extract a **Parsed Statement** from each **E-Statement** for one **Statement Period**, validating that **Stock Holdings**, **Total Asset**, **Margin Debt**, and **Net Asset** all parse correctly."
>
> **Dev:** "And once the schema is stable?"
>
> **Domain expert:** "Then we wire it into the main pipeline: each **E-Statement** becomes a **Raw Payload** under a 元大 **Account**, with a **Source Run** per **Statement Period**. The **Stock Holdings** become **Normalized Holdings** with `asset_type=stock`, and the **Net Asset** populates the **Account Snapshot** total. Daily snapshots between statements forward-fill from the last **Statement Period**."

> **Dev:** "For the **Daily Holding** on 2026-02-15, do we distinguish how many shares are pledged vs owned?"
>
> **Domain expert:** "No — at the daily layer we only track **Total Shares** per symbol. The owned/pledged split only exists at month-end in the **Parsed Statement**. We can't reconstruct when shares moved between categories because the PDF doesn't record that."
>
> **Dev:** "So if the **Cross-Check** fails between February and January, what does that mean?"
>
> **Domain expert:** "It means the implicit Day 0 of February's **Backward Reconstruction** doesn't match January's **Position Anchor**. Either a transaction wasn't captured in the **Parsed Statement**, or there was a corporate action — a stock split, dividend reinvestment — that the PDF doesn't record as a transaction."
>
> **Dev:** "And the **Derived Data** for February lives at `data/derived/yuanta_poc/2026-02/daily_holdings.json`, not under `data/raw/`?"
>
> **Domain expert:** "Correct. **Raw Payloads** are immutable evidence from the source — the PDF and `parsed.json`. **Derived Data** is computed from them and can be regenerated any time. They live in separate directories to make that distinction clear."

## Flagged ambiguities

- **"Account"** appears both as a platform-level account (our domain term) and in generic programming contexts (user account, API account). In this system, **Account** always means a financial account under a **Platform**.
- **"Balance"** is used loosely in API responses to mean either a single asset's quantity or an account's total value. We avoid this term — use **Normalized Holding** for per-asset data and **Account Snapshot** for the aggregate.
- **"Snapshot"** has two levels: **Account Snapshot** (per-account) and **Portfolio Snapshot** (cross-account aggregate). Always qualify which level is meant.
- **"Raw data"** is ambiguous — it could mean the file or the DB metadata record. Use **Raw Payload** for the immutable file content, and **raw_payloads table** for the DB metadata that points to it.
- **"Wallet"** in this system is NOT an Account — a **Wallet Address** is an on-chain address under a Platform. Each Wallet Address is modeled as a separate **Account** in the DB. Don't confuse with exchange "wallet" features (e.g. Binance funding wallet).
- **"總資產 / 資產 / 淨資產"** in broker statements are distinct: **Total Asset** is gross, **Net Asset** is after subtracting **Margin Debt**. Don't conflate. The system's **Account Snapshot** total should map to **Net Asset** for broker accounts (matches what the user actually owns).
- **"對帳單"** is intentionally translated to **E-Statement** (not "Statement" alone) to distinguish from generic API statement responses — it's specifically the encrypted monthly PDF.
- **"Parsed Statement"** is a transitional concept that exists only during the PoC. Once integrated into the main pipeline, it dissolves into **Raw Payload** + **Normalized Holdings**. Don't preserve `parsed.json` as a long-term DB entity.
- **"持倉 / holdings"** is overloaded: at the month-end layer it means **Stock Holding** (owned, with market value) or **Pledged Collateral** (pledged, shares only); at the daily layer it means **Total Shares** (merged, no owned/pledged split). Always qualify which layer is meant.
- **"回推"** (colloquial) maps to **Backward Reconstruction** — avoid using "回推" in code or schema names; use "backward" to make the direction explicit and avoid confusion with "forward" approaches.
- **"Derived Data"** vs **Raw Payload**: both are files on disk, but a Raw Payload is immutable source evidence; Derived Data is computed output that can be regenerated. They must live in separate directory roots (`data/raw/` vs `data/derived/`).
