from tax import RATE


def with_vat(price):
    return round(price * (1 + RATE), 2)
