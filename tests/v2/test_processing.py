from smart_v2.processing.service import ProcessingService


def test_processing_preserves_validated_record():
    service = ProcessingService()

    records = [
        {
            "date": "2020-08-26",
            "symbol_en": "PALAYESH",
            "ins_code": "67675656072510693",
            "record": {
                "pClosing": 100000.0,
                "pDrCotVal": 100000.0,
                "zTotTran": 0.0,
                "qTotTran5J": 0.0,
                "qTotCap": 0.0,
            },
        }
    ]

    result = service.process(records)

    assert len(result) == 1
    assert result[0]["date"] == "2020-08-26"
    assert result[0]["symbol_en"] == "PALAYESH"
    assert result[0]["ins_code"] == "67675656072510693"
    assert result[0]["record"]["pClosing"] == 100000.0
