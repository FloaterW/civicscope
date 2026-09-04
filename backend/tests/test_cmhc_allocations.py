from app.services.cmhc_allocations import allocate_integer_total


def test_largest_remainder_conserves_small_totals():
    allocated = allocate_integer_total(
        10,
        {"tract-a": 100, "tract-b": 80, "tract-c": 20, "tract-d": 5},
    )

    assert sum(allocated.values()) == 10
    assert allocated == {
        "tract-a": 5,
        "tract-b": 4,
        "tract-c": 1,
        "tract-d": 0,
    }


def test_largest_remainder_is_deterministic_for_equal_weights():
    allocated = allocate_integer_total(2, {"tract-c": 0, "tract-a": 0, "tract-b": 0})

    assert allocated == {"tract-c": 0, "tract-a": 1, "tract-b": 1}
    assert sum(allocated.values()) == 2
