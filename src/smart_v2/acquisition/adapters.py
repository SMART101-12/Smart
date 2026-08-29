import pandas as pd
from typing import List, Dict, Any

class DataAdapter:
    @staticmethod
    def tsetmc_to_dataframe(raw_items: List[Dict[str, Any]]) -> pd.DataFrame:
        if not raw_items:
            return pd.DataFrame()
        df = pd.DataFrame(raw_items)
        mapping = {
            'pdrb': 'close',
            'tvol': 'volume',
            'py': 'yesterday_price',
            'pf': 'first_price',
            'pmin': 'low',
            'pmax': 'high'
        }
        df = df.rename(columns=mapping)
        return df

    @staticmethod
    def macro_to_dict(raw_macro: Dict[str, Any]) -> Dict[str, float]:
        return {
            'usd_irr': float(raw_macro.get('usd_irr', 0.0)),
            'usd_tether': float(raw_macro.get('usd_tether', 0.0)),
            'xau_usd': float(raw_macro.get('xau_usd', 0.0)),
            'cbi_rate': float(raw_macro.get('cbi_rate', 0.23))
        }
