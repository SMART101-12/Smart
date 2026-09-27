from smart.tsetmc_adapter import TsetmcAdapter


PRIMARY = {
    "insCode": "primary",
    "lVal18AFC": "پالایش",
    "lVal30": "صندوق پالایشی یکم-بخشی",
    "flow": 1,
    "sourceID": 1,
    "cgrValCot": "51",
}

RIGHT = {
    "insCode": "right",
    "lVal18AFC": "پالایشح",
    "lVal30": "ح . صندوق پالایشی یکم",
    "flow": 1,
    "sourceID": 1,
    "cgrValCot": "51",
}

OPTION = {
    "insCode": "option",
    "lVal18AFC": "ضپلا4000",
    "lVal30": "اختيارخ پالايش-46000-01/04/29",
    "flow": 3,
    "sourceID": 1,
    "cgrValCot": "31",
}


class FakeAdapter(TsetmcAdapter):
    def __init__(self, rows):
        self.rows = rows

    def search(self, query):
        return self.rows


def test_exact_ticker_beats_derivative_and_right():
    adapter = FakeAdapter([RIGHT, OPTION, PRIMARY])
    resolved = adapter.resolve_symbol("پالایش")

    assert resolved["insCode"] == "primary"
    assert resolved["lVal18AFC"] == "پالایش"
    assert resolved["resolver"]["match"] == "exact_ticker"
    assert resolved["resolver"]["candidate_count"] == 3
    assert resolved["resolver"]["excluded_candidate_count"] == 2


def test_exact_name_resolves_primary_instrument():
    adapter = FakeAdapter([RIGHT, PRIMARY])
    resolved = adapter.resolve_symbol("صندوق پالایشی یکم-بخشی")

    assert resolved["insCode"] == "primary"
    assert resolved["resolver"]["match"] == "exact_name"


def test_derivative_only_results_are_rejected():
    adapter = FakeAdapter([OPTION])

    try:
        adapter.resolve_symbol("پالایش")
    except RuntimeError as exc:
        assert "No primary tradable instrument" in str(exc)
    else:
        raise AssertionError("Derivative-only search must not resolve to a primary symbol")


def test_arabic_persian_ticker_variants_resolve_to_same_instrument():
    f_meli = {
        "insCode": "f_meli",
        "lVal18AFC": "فملي",
        "lVal30": "ملي‌ صنايع‌ مس‌ ايران‌",
        "flow": 1,
        "sourceID": 1,
        "cgrValCot": "N1",
    }
    adapter = FakeAdapter([f_meli])

    resolved = adapter.resolve_symbol("فملی")

    assert resolved["insCode"] == "f_meli"
    assert resolved["resolver"]["match"] == "exact_ticker"
    assert resolved["resolver"]["normalized_symbol"] == "فملی"


def test_arabic_kaf_and_yeh_variants_resolve():
    rows = [
        {
            "insCode": "kegol",
            "lVal18AFC": "كگل",
            "lVal30": "گل گهر",
            "flow": 1,
            "sourceID": 1,
            "cgrValCot": "N1",
        },
        {
            "insCode": "ayar",
            "lVal18AFC": "عيار",
            "lVal30": "صندوق سرمایه گذاری طلای عیار",
            "flow": 1,
            "sourceID": 1,
            "cgrValCot": "51",
        },
    ]

    assert FakeAdapter([rows[0]]).resolve_symbol("کگل")["insCode"] == "kegol"
    assert FakeAdapter([rows[1]]).resolve_symbol("عیار")["insCode"] == "ayar"
