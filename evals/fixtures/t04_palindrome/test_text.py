from text import is_palindrome


def test_simple():
    assert is_palindrome("level")


def test_ignores_case_and_spaces():
    assert is_palindrome("Never odd or even")


def test_not_palindrome():
    assert not is_palindrome("python")
