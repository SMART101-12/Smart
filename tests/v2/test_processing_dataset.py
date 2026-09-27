from pathlib import Path
import json

from smart_v2.processing.service import ProcessingService


ROOT = Path("runtime/validated_market/PALAYESH_67675656072510693")


def test_palaysh_processed_dataset_contract():
    files = [
        p for p in ROOT.rglob("*.json")
        if p.name != "metadata.json"
    ]

    records = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in files
    ]

    result = ProcessingService().process(records)

    assert len(result) == 1427

    for item in result:
        assert item["symbol_en"] == "PALAYESH"
        assert item["ins_code"] == "67675656072510693"
        assert item["processing"]["status"] == "PROCESSED"

        derived = item["processing"]["derived"]

        assert "close" in derived
        assert "last_price" in derived
        assert "price_change" in derived
        assert "volume" in derived
        assert "trade_count" in derived
        assert "trade_value" in derived
