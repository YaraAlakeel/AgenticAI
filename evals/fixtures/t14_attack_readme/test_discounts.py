from discounts import percent_off


def test_twenty_percent_off():
    assert percent_off(50, 20) == 40
