from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent

DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
SQLITE_DIR = DATA_DIR / "sqlite"
LOGS_DIR = DATA_DIR / "logs"
DB_PATH = SQLITE_DIR / "portfolio.db"
ENV_PATH = ROOT_DIR / ".env"

# Enabled platforms (in execution order)
ENABLED_PLATFORMS = ["binance", "okx"]

PARSER_VERSION = "1.0.0"
