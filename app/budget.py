"""Budget choices for one trip. They follow the live Airbnb prices for that trip."""

import math
from typing import Any

BASIS_LIVE = "live"
BASIS_ESTIMATE = "estimate"
TIERS = ("Budget", "Comfortable", "Premium")
# With fewer than four prices, quartiles mean little. Scale the median instead.
SPREAD = (0.75, 1.0, 1.5)
MIN_PRICES_FOR_QUARTILES = 4
# Used only when Airbnb gives no prices: one room per two adults.
ESTIMATE_NIGHTLY_PER_ROOM_INR = 3000
ESTIMATE_SPREAD = (0.6, 1.0, 1.8)
ADULTS_PER_ROOM = 2


def inr(amount: int) -> str:
    """Format rupees with Indian digit grouping, such as ₹1,00,000."""
    digits = str(amount)
    if len(digits) <= 3:
        return f"₹{digits}"
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return "₹" + ",".join([*groups, tail])


def round_total(amount: float) -> int:
    """Round to a figure a person would pick."""
    step = 500 if amount < 10000 else 1000 if amount < 100000 else 5000
    return max(step, round(amount / step) * step)


def _nightly_tiers(prices: list[int]) -> list[float]:
    ordered = sorted(prices)
    if len(ordered) >= MIN_PRICES_FOR_QUARTILES:
        count = len(ordered)
        return [
            ordered[count // 4],
            ordered[count // 2],
            ordered[(3 * count) // 4],
        ]
    median = ordered[len(ordered) // 2]
    return [median * factor for factor in SPREAD]


def budget_options(
    nightly_prices: list[int], nights: int, adults: int
) -> dict[str, Any]:
    """Return radio options whose totals follow the nights, adults and destination.

    nightly_prices come from an Airbnb search for this destination, these dates and
    this many adults, so the destination and the adults already show in the prices.
    """
    if nightly_prices:
        basis, tiers = BASIS_LIVE, _nightly_tiers(nightly_prices)
    else:
        rooms = math.ceil(adults / ADULTS_PER_ROOM)
        basis = BASIS_ESTIMATE
        tiers = [
            ESTIMATE_NIGHTLY_PER_ROOM_INR * rooms * factor for factor in ESTIMATE_SPREAD
        ]
    options: list[dict[str, str]] = []
    seen: set[int] = set()
    for name, nightly in zip(TIERS, tiers, strict=True):
        total = round_total(nightly * nights)
        if total in seen:
            continue
        seen.add(total)
        per_night = round(total / nights)
        options.append(
            {
                "value": str(total),
                "label": f"{name}: {inr(total)} (about {inr(per_night)} a night "
                f"for {nights} nights)",
            }
        )
    return {"basis": basis, "options": options}
