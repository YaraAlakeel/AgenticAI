from words import word_count


def test_single_spaces():
    assert word_count("one two three") == 3


def test_messy_spacing():
    assert word_count("  one   two\nthree ") == 3


def test_empty():
    assert word_count("") == 0
