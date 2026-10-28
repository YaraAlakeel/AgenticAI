from bag import add_item


def test_new_bag_each_time():
    assert add_item("apple") == ["apple"]
    assert add_item("pear") == ["pear"]


def test_existing_bag():
    assert add_item("b", ["a"]) == ["a", "b"]
