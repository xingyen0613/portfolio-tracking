from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RunResult:
    source_run_id: str
    platform: str
    account_key: str
    status: str          # 'success' | 'failed'
    error_message: str | None = None


class BaseConnector(ABC):
    platform_name: str
    account_key: str = "account_main"
    use_pricer: bool = True  # set False to skip market price enrichment

    @abstractmethod
    def authenticate(self) -> None:
        """Load credentials and initialize API client."""

    @abstractmethod
    def fetch_raw(self) -> list[dict]:
        """
        Call platform API and return list of raw payloads.
        Each item: {'resource_type': str, 'payload': dict, 'fetched_at': str}
        """

    @abstractmethod
    def parse_holdings(self, raw_payloads: list[dict]) -> list[dict]:
        """
        Parse raw payloads into normalized holdings.
        Each item must include:
            platform_symbol, asset_type, quantity, price, value,
            original_currency, price_source (optional)
        """

    def run(self, batch_id: str, user_id: str) -> RunResult:
        """Full pipeline: authenticate → fetch → store raw → parse → snapshot."""
        from app.ingest.pipeline import run_source_pipeline
        return run_source_pipeline(self, batch_id, user_id)
