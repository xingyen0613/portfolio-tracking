import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")

DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
SQLITE_DIR = DATA_DIR / "sqlite"
LOGS_DIR = DATA_DIR / "logs"
DB_PATH = SQLITE_DIR / "portfolio.db"
ENV_PATH = ROOT_DIR / ".env"
WALLETS_ENV_PATH = ROOT_DIR / "config" / ".env.wallets"

# Enabled platforms (in execution order)
ENABLED_PLATFORMS = ["binance", "okx", "mexc", "bybit", "sui_wallet", "sol_wallet", "ibkr", "evm_wallet"]

# SUI DeFi protocols — 預留供後續版本使用，目前 connector 尚未支援
# SUI_DEFI_PROTOCOLS = ["cetus", "navi", "suilend", "typus", "scallop", "walrus"]

PARSER_VERSION = "1.0.0"

# Dashboard settings
DASHBOARD_PORT = 857

# Platform → asset category mapping
PLATFORM_CATEGORY = {
    "binance": "crypto",
    "okx": "crypto",
    "mexc": "crypto",
    "bybit": "crypto",
    "sui_wallet": "crypto",
    "sol_wallet": "crypto",
    "evm_wallet": "crypto",
    "yuanta": "tw_stock",
    "firsttrade": "us_stock",
    "ibkr": "us_stock",
}

CATEGORY_LABEL = {
    "crypto": "幣圈",
    "tw_stock": "台股",
    "us_stock": "美股",
}

# Exchange rate (TWD per USD) — hardcoded until live FX API is added
TWD_PER_USD: float = 31.5

# PostgreSQL connection (production & local Docker)
DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    "postgresql://portfolio:portfolio_dev@localhost:5432/portfolio",
)

# Fixed UUID for the system owner (developer's data before multi-user launch)
SYSTEM_OWNER_ID = "00000000-0000-0000-0000-000000000001"

# Auth
GOOGLE_CLIENT_ID: str = os.environ.get("GOOGLE_CLIENT_ID", "")
JWT_SECRET: str = os.environ.get("JWT_SECRET", "dev-secret-change-in-prod")
JWT_EXPIRE_DAYS: int = 30
OWNER_GOOGLE_EMAIL: str = os.environ.get("OWNER_GOOGLE_EMAIL", "")
