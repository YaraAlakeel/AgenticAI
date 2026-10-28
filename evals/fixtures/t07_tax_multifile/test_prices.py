from prices import with_vat


def test_vat_is_15_percent():
    assert with_vat(100) == 115.0
