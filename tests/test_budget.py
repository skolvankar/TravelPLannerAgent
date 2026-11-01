import pytest

from app.budget import build_budget_options, estimated_options, format_inr, live_options


@pytest.mark.parametrize(
    ("amount", "text"),
    [
        (500, "₹500"),
        (12500, "₹12,500"),
        (100000, "₹1,00,000"),
        (12345678, "₹1,23,45,678"),
    ],
)
def test_format_inr_uses_indian_groups(amount: int, text: str) -> None:
    assert format_inr(amount) == text


def test_live_options_use_percentiles_and_round_up() -> None:
    options = live_options([10000, 20000, 30000, 40000, 50001])
    assert options == [
        {"value": "20000", "label": "Economy: ₹20,000"},
        {"value": "30000", "label": "Mid-range: ₹30,000"},
        {"value": "40000", "label": "Comfort: ₹40,000"},
        {"value": "46500", "label": "Premium: ₹46,500"},
    ]


def test_live_options_follow_the_prices_of_the_location() -> None:
    cheap = live_options([1000, 2000, 3000, 4000])
    costly = live_options([10000, 20000, 30000, 40000])
    assert int(costly[0]["value"]) > int(cheap[-1]["value"])


def test_live_options_need_enough_prices() -> None:
    assert live_options([10000, 20000, 30000]) == []


def test_live_options_remove_repeated_values() -> None:
    values = [o["value"] for o in live_options([10000, 10000, 10000, 10000, 90000])]
    assert len(values) == len(set(values))


def test_live_options_need_two_distinct_values() -> None:
    assert live_options([10000] * 8) == []


def test_estimate_grows_with_nights_and_rooms() -> None:
    base = int(estimated_options(1, 2)[0]["value"])
    assert base == 2000
    assert int(estimated_options(3, 2)[0]["value"]) == base * 3
    assert int(estimated_options(1, 3)[0]["value"]) == base * 2


def test_build_uses_live_prices_when_possible() -> None:
    options, live = build_budget_options([10000, 20000, 30000, 40000], 3, 2)
    assert live is True
    assert options == live_options([10000, 20000, 30000, 40000])


def test_build_uses_estimate_with_no_prices() -> None:
    options, live = build_budget_options([], 3, 2)
    assert live is False
    assert options == estimated_options(3, 2)
