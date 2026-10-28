from slug import slugify


def test_basic():
    assert slugify("Hello, World!") == "hello-world"


def test_extra_spaces():
    assert slugify("  Agentic   AI  ") == "agentic-ai"
