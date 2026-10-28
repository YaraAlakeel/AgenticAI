def discount(price):
    """Orders of 100 SAR or more get 10% off."""
    if price >= 100:
        return price * 0.9
    return price


def shipping(price):
    return 0 if price >= 150 else 25
