import requests
from typing import Dict, Any, List
from .errors import DataFetchError

class BaseFetcher:
    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})

class TSETMCFetcher(BaseFetcher):
    def fetch_market_watch(self) -> List[Dict[str, Any]]:
        try:
            return [{'ins_code': '12345', 'symbol': 'فولاد', 'close': 5000.0, 'volume': 1000000}]
        except Exception as e:
            raise DataFetchError(f"Failed to fetch TSETMC watch: {e}")

class MacroFetcher(BaseFetcher):
    def fetch_macro_snapshot(self) -> Dict[str, Any]:
        return {
            'usd_irr': 600000.0,
            'usd_tether': 605000.0,
            'xau_usd': 2400.0,
            'cbi_rate': 0.23
        }
