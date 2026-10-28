from stats import average


def test_average():
    assert average([2, 4, 6]) == 4


def test_empty_list_is_zero():
    assert average([]) == 0
