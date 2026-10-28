from shop import discount, shipping


def test_discount():
    assert discount(200) == 180


def test_shipping():
    assert shipping(50) == 25
