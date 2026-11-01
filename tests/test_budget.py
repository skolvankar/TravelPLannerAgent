from app.budget import budget_options, format_inr, nightly_rate
from app.config import DEFAULT_NIGHTLY_INR, DESTINATION_NIGHTLY_INR


def values(destination: str, nights: int, adults: int) -> list[int]:
    return [int(value) for value, _ in budget_options(destination, nights, adults)]


def test_options_grow_with_nights_and_rooms() -> None:
    base = values("Goa", 2, 2)
    assert all(more > less for more, less in zip(values("Goa", 4, 2), base))
    # Three adults need a second room. Two adults share one.
    assert values("Goa", 2, 3) == values("Goa", 4, 2)
    assert values("Goa", 2, 1) == base


def test_options_depend_on_the_place() -> None:
    assert values("Mumbai", 3, 2) > values("Rishikesh", 3, 2)


def test_place_names_match_loosely_and_unknown_places_use_the_default() -> None:
    assert nightly_rate(" North Goa ") == DESTINATION_NIGHTLY_INR["goa"]
    assert nightly_rate("Atlantis") == DEFAULT_NIGHTLY_INR


def test_options_are_rounded_distinct_and_ascending() -> None:
    for nights, adults in ((1, 1), (3, 2), (14, 16)):
        totals = values("Goa", nights, adults)
        assert totals == sorted(set(totals))
        assert all(total % 500 == 0 for total in totals)
        assert len(totals) == 4


def test_label_shows_total_and_nightly_price() -> None:
    value, label = budget_options("Goa", 3, 2)[1]
    # 4,500 x 3 nights = 13,500, rounded to the nearest 1,000.
    assert value == "14000"
    assert label == "Standard: ₹14,000 for 3 nights (about ₹4,666 a night)"
    assert "1 night " in budget_options("Goa", 1, 2)[0][1]


def test_format_inr_uses_indian_groups() -> None:
    assert format_inr(500) == "₹500"
    assert format_inr(13500) == "₹13,500"
    assert format_inr(100000) == "₹1,00,000"
    assert format_inr(12345678) == "₹1,23,45,678"
