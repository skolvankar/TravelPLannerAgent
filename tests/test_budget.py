import json
from collections.abc import Callable
from typing import Any

import anthropic
import httpx2
import pytest

from app import budget
from app.budget import budget_options, estimate_rates, format_inr
from app.config import DEFAULT_NIGHTLY_RATES

RATES = {"budget": 1000, "mid_range": 2000, "premium": 4000, "luxury": 8000}


def values(options: list[dict[str, str]]) -> list[int]:
    return [int(option["value"]) for option in options]


@pytest.mark.parametrize(
    ("amount", "text"),
    [
        (500, "₹500"),
        (12000, "₹12,000"),
        (100000, "₹1,00,000"),
        (12345678, "₹1,23,45,678"),
    ],
)
def test_format_inr_uses_indian_digit_groups(amount: int, text: str) -> None:
    assert format_inr(amount) == text


def test_options_multiply_rate_by_rooms_and_nights() -> None:
    assert values(budget_options(RATES, 3, 2)) == [3000, 6000, 12000, 24000]
    assert values(budget_options(RATES, 1, 2)) == [1000, 2000, 4000, 8000]


@pytest.mark.parametrize(("adults", "rooms"), [(1, 1), (2, 1), (3, 2), (5, 3)])
def test_two_adults_share_one_room(adults: int, rooms: int) -> None:
    assert values(budget_options(RATES, 1, adults))[0] == 1000 * rooms


def test_options_change_with_destination_rates() -> None:
    pricier = {key: value * 3 for key, value in RATES.items()}
    assert values(budget_options(pricier, 3, 2)) == [9000, 18000, 36000, 72000]


def test_totals_round_to_500_and_labels_explain_them() -> None:
    rates = {"budget": 1234, "mid_range": 2000, "premium": 4000, "luxury": 8000}
    options = budget_options(rates, 1, 3)
    assert options[0]["value"] == "2500"
    assert options[0]["label"] == "Budget · ₹2,500 (2 rooms at ₹1,234 a night, 1 night)"


def test_levels_that_round_to_one_total_appear_once() -> None:
    rates = {"budget": 600, "mid_range": 700, "premium": 4000, "luxury": 8000}
    assert values(budget_options(rates, 1, 1)) == [500, 4000, 8000]


async def test_no_api_key_uses_default_rates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert await estimate_rates("Goa") == DEFAULT_NIGHTLY_RATES


def _message(text: str, stop_reason: str = "end_turn") -> dict[str, Any]:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-5-5",
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }


def _fake_client(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx2.Request], httpx2.Response],
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-value")
    real = anthropic.AsyncAnthropic

    def build() -> anthropic.AsyncAnthropic:
        http_client = anthropic.DefaultAsyncHttpxClient(
            transport=httpx2.MockTransport(handler)
        )
        return real(http_client=http_client, max_retries=0)

    monkeypatch.setattr(budget.anthropic, "AsyncAnthropic", build)


async def test_estimate_sends_destination_as_user_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: dict[str, Any] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.update(json.loads(request.content))
        return httpx2.Response(200, json=_message(json.dumps(RATES)))

    _fake_client(monkeypatch, handler)
    assert await estimate_rates("Paris") == RATES
    assert sent["model"] == "claude-haiku-5-5"
    assert sent["messages"] == [{"role": "user", "content": "Paris"}]
    assert "Paris" not in json.dumps(sent["system"])
    assert sent["output_config"]["format"]["type"] == "json_schema"


@pytest.mark.parametrize(
    "rates",
    [
        {"budget": 4000, "mid_range": 2000, "premium": 6000, "luxury": 8000},
        {"budget": 100, "mid_range": 2000, "premium": 4000, "luxury": 8000},
        {"budget": 1000, "mid_range": 2000, "premium": 4000, "luxury": 9_000_000},
    ],
)
async def test_unusable_rates_fall_back_to_defaults(
    monkeypatch: pytest.MonkeyPatch, rates: dict[str, int]
) -> None:
    body = _message(json.dumps(rates))
    _fake_client(monkeypatch, lambda r: httpx2.Response(200, json=body))
    assert await estimate_rates("Goa") == DEFAULT_NIGHTLY_RATES


async def test_api_error_falls_back_to_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = {"type": "error", "error": {"type": "api_error", "message": "down"}}
    _fake_client(monkeypatch, lambda r: httpx2.Response(500, json=body))
    assert await estimate_rates("Goa") == DEFAULT_NIGHTLY_RATES


async def test_refusal_falls_back_to_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    body = {**_message("", "refusal"), "content": []}
    _fake_client(monkeypatch, lambda r: httpx2.Response(200, json=body))
    assert await estimate_rates("Goa") == DEFAULT_NIGHTLY_RATES
