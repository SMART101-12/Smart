from .service import AcquisitionService, get_macro_data, get_stock_data
from .fetchers import TSETMCFetcher, MacroFetcher
from .normalizer import DataNormalizer
from .adapters import DataAdapter
from smart.global_market import FREDClient, GlobalMarketArchive, GlobalObservation

__all__ = [
    "AcquisitionService",
    "get_stock_data",
    "get_macro_data",
    "TSETMCFetcher",
    "MacroFetcher",
    "DataNormalizer",
    "DataAdapter",
    "FREDClient",
    "GlobalMarketArchive",
    "GlobalObservation",
]
