from smart.persian_text import normalize_persian_text


def test_common_arabic_persian_variants():
    assert normalize_persian_text("فملي") == "فملی"
    assert normalize_persian_text("كگل") == "کگل"
    assert normalize_persian_text("كچاد") == "کچاد"
    assert normalize_persian_text("عيار") == "عیار"


def test_normalization_keeps_normal_persian_text_stable():
    assert normalize_persian_text("فملی") == "فملی"
    assert normalize_persian_text("شپنا") == "شپنا"


def test_normalization_strips_kashida_and_outer_whitespace():
    assert normalize_persian_text("  فـملی  ") == "فملی"
