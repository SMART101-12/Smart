# -*- coding: utf-8 -*-
"""smart_v2.analysis package — clean UTF-8 (no BOM)."""
from .smart_money import SmartMoneyAnalyzer
from .gold_fund import GoldFundAnalyzer
from .multi_factor_engine import MultiFactorEngine
from .stock_service import StockAnalysisService

__all__ = [
    "SmartMoneyAnalyzer",
    "GoldFundAnalyzer",
    "MultiFactorEngine",
    "StockAnalysisService",
]
__version__ = "2.0.0"
