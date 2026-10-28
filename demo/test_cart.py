from cart import apply_discount, subtotal, total

ITEMS = [{"name": "coffee", "price": 10.0, "qty": 2}, {"name": "cake", "price": 15.0, "qty": 1}]


def test_subtotal_uses_quantity():
    assert subtotal(ITEMS) == 35.0


def test_discount_is_a_percentage():
    assert apply_discount(200, 10) == 180


def test_total_with_vat_and_discount():
    assert total(ITEMS, discount_percent=20) == 32.2
