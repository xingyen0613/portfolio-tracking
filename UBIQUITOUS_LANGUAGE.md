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

## Pipeline Layers (within a Connector)

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Auth** | The layer that reads secrets, builds API clients, and handles signing/tokens | Login, session, credentials |
| **Fetch** | The layer that calls platform APIs and returns raw responses — no persistence logic | Request, call, pull |
| **Ingest** | The layer that persists Raw Payloads, records metadata, and performs minimal validation | Store, save, write |

## Relationships

- A **Batch** contains one or more **Source Runs**, one per enabled **Platform**-**Account** pair
- A **Source Run** produces exactly one **Raw Payload** (stored as an immutable file)
- A **Raw Payload** is processed by a **Parser** to produce one or more **Normalized Holdings**
- All **Normalized Holdings** from a single **Source Run** form one **Account Snapshot**
- All **Account Snapshots** within a **Batch** can be aggregated into a **Portfolio Snapshot**
- A **Connector** encapsulates the **Auth** / **Fetch** / **Ingest** layers for one **Platform**

## Example dialogue

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

## Flagged ambiguities

- **"Account"** appears both as a platform-level account (our domain term) and in generic programming contexts (user account, API account). In this system, **Account** always means a financial account under a **Platform**.
- **"Balance"** is used loosely in API responses to mean either a single asset's quantity or an account's total value. We avoid this term — use **Normalized Holding** for per-asset data and **Account Snapshot** for the aggregate.
- **"Snapshot"** has two levels: **Account Snapshot** (per-account) and **Portfolio Snapshot** (cross-account aggregate). Always qualify which level is meant.
- **"Raw data"** is ambiguous — it could mean the file or the DB metadata record. Use **Raw Payload** for the immutable file content, and **raw_payloads table** for the DB metadata that points to it.
