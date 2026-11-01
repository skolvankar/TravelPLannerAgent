"""Budget options that depend on the place, the stay length, and the adults."""

import math

from app.config import (
    ADULTS_PER_ROOM,
    BUDGET_TIERS,
    DEFAULT_NIGHTLY_INR,
    DESTINATION_NIGHTLY_INR,
)


def nightly_rate(destination: str) -> int:
    """Return the room rate for a known place, or the default rate."""
    name = destination.strip().lower()
    if name in DESTINATION_NIGHTLY_INR:
        return DESTINATION_NIGHTLY_INR[name]
    # "North Goa" or "Goa, India" still match goa.
    for place, rate in DESTINATION_NIGHTLY_INR.items():
        if place in name:
            return rate
    return DEFAULT_NIGHTLY_INR


def format_inr(amount: int) -> str:
    """Format with Indian digit groups, such as ₹1,00,000."""
    digits = str(amount)
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return "₹" + ",".join([*groups, tail])


def _round_amount(amount: float) -> int:
    step = 500 if amount < 10000 else 1000
    return max(step, round(amount / step) * step)


def budget_options(destination: str, nights: int, adults: int) -> list[tuple[str, str]]:
    """Return (value, label) pairs for the whole-stay budget, smallest first."""
    rooms = math.ceil(adults / ADULTS_PER_ROOM)
    base = nightly_rate(destination) * rooms * nights
    options: list[tuple[str, str]] = []
    seen: set[int] = set()
    for tier, multiplier in BUDGET_TIERS:
        total = _round_amount(base * multiplier)
        if total in seen:
            continue
        seen.add(total)
        night_word = "night" if nights == 1 else "nights"
        label = (
            f"{tier}: {format_inr(total)} for {nights} {night_word} "
            f"(about {format_inr(total // nights)} a night)"
        )
        options.append((str(total), label))
    return options
