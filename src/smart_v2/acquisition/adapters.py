from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

class DataAdapter:
    @staticmethod
    def _coalesce(df: pd.DataFrame, candidates: tuple[str, ...]) -> pd.Series:
        """Choose the first usable value per row across TSETMC aliases.

        MarketWatch emits compact fields alongside verbose fields.  During a
        closed session the verbose quote fields can legitimately be zero while
        the compact closing/volume fields still contain the latest observation,
        so a simple column rename is not sufficient.
        """
        result = pd.Series([None] * len(df), index=df.index, dtype="object")
        for candidate in candidates:
            if candidate not in df.columns:
                continue
            values = df[candidate]
            usable = values.notna() & (values != "")
            current_numeric = pd.to_numeric(result, errors="coerce")
            # A zero quote is often a placeholder in the closed-session
            # verbose fields.  Treat it as missing while looking for a
            # non-zero compact alias; if no alias exists, the zero remains.
            missing = result.isna() | (result == "")
            zero_placeholder = current_numeric.notna() & (current_numeric == 0)
            replaceable = missing | zero_placeholder
            result = result.where(~(replaceable & usable), values)
        return result

    @staticmethod
    def tsetmc_to_dataframe(raw_items: List[Dict[str, Any]]) -> pd.DataFrame:
        if not raw_items:
            return pd.DataFrame()
        df = pd.DataFrame(raw_items)
        # TSETMC exposes two families of field names: compact MarketWatch
        # names (``pc``, ``qtj``...) and the verbose closing-price names
        # (``pClosing``, ``qTotTran5J``...).  Normalize both without dropping
        # the original columns so raw provenance remains available.
        aliases: dict[str, tuple[str, ...]] = {
            "symbol": ("symbol", "lVal18AFC", "lva", "lVal18"),
            "ins_code": ("ins_code", "insCode", "insID"),
            "date": ("date", "dEven"),
            "open": ("open", "pOpen", "pFirst", "pf"),
            "high": ("high", "pHigh", "pMax", "pmax", "pmx"),
            "low": ("low", "pLow", "pMin", "pmin", "pmn"),
            # ``pc`` is price change, not close.  ``pcl`` is the compact
            # MarketWatch closing-price field.
            "close": ("close", "pClosing", "pcl", "pDrCotVal", "pdv", "pdrb"),
            "last_price": ("last_price", "pDrCotVal", "pdv", "pl"),
            "yesterday_price": ("yesterday_price", "pYesterday", "py"),
            "volume": ("volume", "qTotTran5J", "qtj", "tvol"),
            "value": ("value", "qTotCap", "qtc", "tval"),
            "trades": ("trades", "zTotTran", "ztt", "tno"),
        }
        for target, candidates in aliases.items():
            if target in df.columns:
                continue
            df[target] = DataAdapter._coalesce(df, candidates)
        return df

    @staticmethod
    def macro_to_dict(raw_macro: Dict[str, Any]) -> Dict[str, float]:
        return {
            "usd_irr": float(raw_macro.get("usd_irr", 0.0)),
            "usd_tether": float(raw_macro.get("usd_tether", 0.0)),
            "xau_usd": float(raw_macro.get("xau_usd", 0.0)),
            "cbi_rate": float(raw_macro.get("cbi_rate", 0.23)),
        }
