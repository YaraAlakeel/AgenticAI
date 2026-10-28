from settings import merge_settings


def test_user_overrides_default():
    merged = merge_settings({"theme": "dark"})
    assert merged["theme"] == "dark"
    assert merged["language"] == "en"
