import pytest
import pandas as pd
from src.smart_v2.acquisition.adapters import DataAdapter
from src.smart_v2.acquisition.normalizer import DataNormalizer
from src.smart_v2.acquisition.service import AcquisitionService
from src.smart_v2.acquisition.errors import ValidationError

def test_adapter_tsetmc_mapping():
    raw = [{'tvol': 500, 'pdrb': 1200, 'symbol': 'TEST'}]
    df = DataAdapter.tsetmc_to_dataframe(raw)
    assert 'volume' in df.columns
    assert 'close' in df.columns
    assert df.iloc[0]['volume'] == 500

def test_adapter_macro_mapping():
    raw = {'usd_irr': '620000', 'usd_tether': 621000, 'xau_usd': 2450.5}
    res = DataAdapter.macro_to_dict(raw)
    assert res['usd_irr'] == 620000.0
    assert res['xau_usd'] == 2450.5
    assert res['cbi_rate'] == 0.23

def test_normalizer_clean_ohlcv():
    df = pd.DataFrame({
        'close': [100.0, -10.0, None, 200.0],
        'volume': [10, 20, 30, 40]
    })
    clean = DataNormalizer.clean_ohlcv(df)
    assert len(clean) == 2
    assert list(clean['close']) == [100.0, 200.0]

def test_normalizer_missing_columns():
    df = pd.DataFrame({'open': [100, 200]})
    with pytest.raises(ValidationError):
        DataNormalizer.clean_ohlcv(df)

def test_acquisition_service_integration():
    svc = AcquisitionService()
    df = svc.get_stock_data()
    assert not df.empty
    assert 'close' in df.columns
    
    macro = svc.get_macro_data()
    assert 'usd_irr' in macro
    assert macro['usd_irr'] > 0
