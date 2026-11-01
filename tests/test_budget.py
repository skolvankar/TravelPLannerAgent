from app.airbnb import parse_nightly_price, parse_nightly_prices
from app.budget import BASIS_ESTIMATE, BASIS_LIVE, budget_options, inr, round_total


def totals(result: dict) -> list[int]:
    return [int(option["value"]) for option in result["options"]]


def test_indian_digit_grouping() -> None:
    assert inr(950) == "₹950"
    assert inr(10000) == "₹10,000"
    assert inr(100000) == "₹1,00,000"
    assert inr(12345678) == "₹1,23,45,678"


def test_round_total_uses_clean_steps() -> None:
    assert round_total(4321) == 4500
    assert round_total(43210) == 43000
    assert round_total(432100) == 430000
    assert round_total(1) == 500


def test_options_follow_the_live_prices_and_the_nights() -> None:
    prices = [2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000]
    short = budget_options(prices, 2, 2)
    long = budget_options(prices, 6, 2)
    assert short["basis"] == BASIS_LIVE
    assert totals(short) == sorted(totals(short))
    assert totals(long)[1] == 3 * totals(short)[1]


def test_more_expensive_destinations_get_higher_options() -> None:
    cheap = budget_options([1500, 2000, 2500, 3000], 3, 2)
    dear = budget_options([9000, 12000, 15000, 18000], 3, 2)
    assert min(totals(dear)) > max(totals(cheap))


def test_few_prices_still_give_ordered_options() -> None:
    result = budget_options([4000], 3, 2)
    assert result["basis"] == BASIS_LIVE
    assert totals(result) == sorted(set(totals(result)))
    assert len(totals(result)) == 3


def test_labels_show_the_nights_and_nightly_price() -> None:
    label = budget_options([4000, 5000, 6000, 7000], 3, 2)["options"][0]["label"]
    assert "3 nights" in label
    assert "a night" in label


def test_estimate_grows_with_adults() -> None:
    two = budget_options([], 3, 2)
    five = budget_options([], 3, 5)
    assert two["basis"] == BASIS_ESTIMATE
    assert min(totals(five)) > min(totals(two))


def test_options_are_always_positive_and_unique() -> None:
    for prices in ([], [1], [1, 1, 1, 1], [500000] * 5):
        result = budget_options(prices, 1, 1)
        values = totals(result)
        assert values and all(v > 0 for v in values)
        assert len(values) == len(set(values))


def test_price_label_to_nightly_price() -> None:
    assert parse_nightly_price("₹17,565 for 3 nights") == 5855
    assert parse_nightly_price("₹13,894 for 3 nights, originally ₹15,393") == 4631
    assert parse_nightly_price("₹4,500 per night") == 4500
    assert parse_nightly_price("Price not shown") is None
    assert parse_nightly_price("₹4,500") is None
    assert parse_nightly_price(None) is None


def test_nightly_prices_skip_results_without_a_price() -> None:
    def result(label: str | None) -> dict:
        primary = {"accessibilityLabel": label} if label else {}
        return {"structuredDisplayPrice": {"primaryLine": primary}}

    payload = {
        "searchResults": [result("₹6,000 for 2 nights"), result(None), {}]
        + [result("₹9,000 for 3 nights")]
    }
    assert parse_nightly_prices(payload) == [3000, 3000]
    assert parse_nightly_prices({}) == []
