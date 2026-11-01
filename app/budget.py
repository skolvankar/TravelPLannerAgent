"""Build the budget options from stay duration, adults, and live prices for a location."""

import math
from statistics import quantiles

from app.config import (
    ADULTS_PER_ROOM,
    BUDGET_MIN_PRICES,
    BUDGET_ROUND_INR,
    BUDGET_TIERS,
)


def format_inr(amount: int) -> str:
    """Write rupees with Indian digit groups, such as ₹1,00,000."""
    digits = str(amount)
    if len(digits) <= 3:
        return f"₹{digits}"
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while head:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return f"₹{','.join(groups)},{tail}"


def _options(amounts: list[tuple[str, int]]) -> list[dict[str, str]]:
    return [
        {"value": str(amount), "label": f"{name}: {format_inr(amount)}"}
        for name, amount in amounts
    ]


def live_options(totals: list[int]) -> list[dict[str, str]]:
    """Return one option for each distinct percentile, or nothing if data is thin."""
    if len(totals) < BUDGET_MIN_PRICES:
        return []
    cuts = quantiles(totals, n=100, method="inclusive")
    amounts: list[tuple[str, int]] = []
    for name, percentile, _ in BUDGET_TIERS:
        rounded = math.ceil(cuts[percentile - 1] / BUDGET_ROUND_INR) * BUDGET_ROUND_INR
        if not amounts or rounded != amounts[-1][1]:
            amounts.append((name, rounded))
    return _options(amounts) if len(amounts) > 1 else []


def estimated_options(nights: int, adults: int) -> list[dict[str, str]]:
    """Return general estimates. This formula does not use the location."""
    rooms = math.ceil(adults / ADULTS_PER_ROOM)
    return _options([(name, rooms * rate * nights) for name, _, rate in BUDGET_TIERS])


def build_budget_options(
    totals: list[int], nights: int, adults: int
) -> tuple[list[dict[str, str]], bool]:
    """Return the options, and whether they come from live prices."""
    options = live_options(totals)
    if options:
        return options, True
    return estimated_options(nights, adults), False
