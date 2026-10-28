def add_item(item, bag=[]):
    """Add item to bag and return it. Each call without a bag starts a new one."""
    bag.append(item)
    return bag
