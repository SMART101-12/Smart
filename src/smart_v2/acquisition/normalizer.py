import pandas as pd
from .errors import ValidationError

class DataNormalizer:
    @staticmethod
    def clean_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            raise ValidationError("Empty DataFrame provided.")
        
        required = ['close', 'volume']
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValidationError(f"Missing required columns: {missing}")
        
        df = df.copy()
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        df = df.dropna(subset=['close', 'volume'])
        df = df[df['close'] > 0]
        return df
