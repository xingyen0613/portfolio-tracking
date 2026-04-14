from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent

DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
SQLITE_DIR = DATA_DIR / "sqlite"
LOGS_DIR = DATA_DIR / "logs"
DB_PATH = SQLITE_DIR / "portfolio.db"
ENV_PATH = ROOT_DIR / ".env"

# Enabled platforms (in execution order)
ENABLED_PLATFORMS = ["binance", "okx", "sui_wallet"]

# SUI DeFi protocols — 預留供後續版本使用，目前 connector 尚未支援
# SUI_DEFI_PROTOCOLS = ["cetus", "navi", "suilend", "typus", "scallop", "walrus"]

PARSER_VERSION = "1.0.0"

# Dashboard settings
DASHBOARD_PORT = 857

# Platform → asset category mapping
PLATFORM_CATEGORY = {
    "binance": "crypto",
    "okx": "crypto",
    "sui_wallet": "crypto",
    "yuanta": "tw_stock",
    "firsttrade": "us_stock",
}

CATEGORY_LABEL = {
    "crypto": "幣圈",
    "tw_stock": "台股",
    "us_stock": "美股",
}

# Exchange rate (TWD per USD) — hardcoded until live FX API is added
TWD_PER_USD: float = 31.5
