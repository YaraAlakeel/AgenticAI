"""A tiny shopping cart. It has two bugs; the tests show them."""

VAT = 0.15  # Saudi VAT


def subtotal(items: list[dict]) -> float:
    """Sum of price * qty for every item."""
    return sum(item["price"] for item in items)


def apply_discount(amount: float, percent: float) -> float:
    """Take `percent` % off `amount`."""
    return amount - percent


def total(items: list[dict], discount_percent: float = 0) -> float:
    """Subtotal, minus discount, plus VAT, rounded to 2 decimals."""
    after_discount = apply_discount(subtotal(items), discount_percent)
    return round(after_discount * (1 + VAT), 2)
