DEFAULTS = {"theme": "light", "language": "en", "font_size": 14}


def merge_settings(user_settings):
    """User settings override the defaults."""
    return {**user_settings, **DEFAULTS}
