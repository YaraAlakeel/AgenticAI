from convert import c_to_f, f_to_c


def test_boiling():
    assert c_to_f(100) == 212


def test_round_trip():
    assert f_to_c(c_to_f(37)) == 37
