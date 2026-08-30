import pandas as pd
from typing import Dict, Any
from .fetchers import TSETMCFetcher, MacroFetcher
from .adapters import DataAdapter
from .normalizer import DataNormalizer

class AcquisitionService:
    def __init__(self, tsetmc_fetcher=None, macro_fetcher=None):
        self.tsetmc = tsetmc_fetcher or TSETMCFetcher()
        self.macro = macro_fetcher or MacroFetcher()
        self.adapter = DataAdapter()
        self.normalizer = DataNormalizer()

    def get_stock_data(self) -> pd.DataFrame:
        raw = self.tsetmc.fetch_market_watch()
        df = self.adapter.tsetmc_to_dataframe(raw)
        return self.normalizer.clean_ohlcv(df)

    def get_macro_data(self) -> Dict[str, float]:
        raw = self.macro.fetch_macro_snapshot()
        return self.adapter.macro_to_dict(raw)


def get_stock_data() -> pd.DataFrame:
    """Compatibility convenience function for the V2 pipeline."""
    return AcquisitionService().get_stock_data()


def get_macro_data() -> Dict[str, float]:
    """Compatibility convenience function for the V2 pipeline."""
    return AcquisitionService().get_macro_data()


__all__ = ["AcquisitionService", "get_stock_data", "get_macro_data"]
