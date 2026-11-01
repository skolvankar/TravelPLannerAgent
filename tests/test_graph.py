import asyncio
import json
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import anthropic
import httpx2
import pytest

from app import graph
from app.events import hub
from app.graph import (
    TripSpec,
    budget_options,
    check_spec,
    live_totals,
    parse_answers,
    resume_trip,
    start_trip,
)

TODAY = date.today()
CHECK_IN = TODAY + timedelta(days=30)
CHECK_OUT = CHECK_IN + timedelta(days=3)
LISTING = {"id": "1", "name": "Stay", "url": "https://x.test/1"}
PLACE = {"title": "Beach", "url": "https://x.test/p", "summary": "Sand"}
ANSWERS = {
    "check_in": CHECK_IN.isoformat(),
    "check_out": CHECK_OUT.isoformat(),
    "adults": "2",
    "budget_total_inr": "25000",
}
RATES = [1000, 2000, 4000, 8000]
PRICES = [4000, 6000, 8000, 10000, 12000, 20000, 30000, 50000, 90000]
SECRET_QUERY = "Goa trip, my PAN placeholder is XXXXX"

Fakes = tuple[dict[str, Any], dict[str, TripSpec]]


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> Fakes:
    calls: dict[str, Any] = {
        "extract": 0,
        "estimate": [],
        "prices": [],
        "price_list": PRICES,
        "search": [],
        "places": [],
        "concurrent": 0,
    }
    spec = {"value": TripSpec(destination="Goa", interests=["beach"])}

    async def fake_extract(query: str) -> TripSpec:
        calls["extract"] += 1
        return spec["value"]

    async def fake_estimate(destination: str) -> list[int]:
        calls["estimate"].append(destination)
        return RATES

    async def fake_prices(**kwargs: Any) -> dict[str, Any]:
        calls["prices"].append(kwargs)
        return {"prices": calls["price_list"]}

    async def fake_search(**kwargs: Any) -> dict[str, Any]:
        calls["search"].append(kwargs)
        calls["concurrent"] += 1
        await asyncio.sleep(0)
        calls["overlap"] = calls["concurrent"] == 2
        calls["concurrent"] -= 1
        return {"listings": [LISTING], "source": "live"}

    async def fake_places(destination: str, interests: list[str]) -> dict[str, Any]:
        calls["places"].append((destination, interests))
        calls["concurrent"] += 1
        await asyncio.sleep(0)
        calls["concurrent"] -= 1
        return {"places": [PLACE], "available": True}

    monkeypatch.setattr(graph, "extract_trip", fake_extract)
    monkeypatch.setattr(graph, "estimate_rates", fake_estimate)
    monkeypatch.setattr(graph, "stay_prices", fake_prices)
    monkeypatch.setattr(graph, "search_stays", fake_search)
    monkeypatch.setattr(graph, "search_places", fake_places)
    return calls, spec


async def answer_all(run: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Answer each question in turn. Return the last run and the fields asked."""
    asked = []
    while run["status"] == "needs_input":
        asked.append(run["field"])
        answer = {run["field"]: ANSWERS[run["field"]]}
        run = await resume_trip(run["thread_id"], answer)
    return run, asked


def full_spec() -> TripSpec:
    return TripSpec(
        destination="Goa",
        check_in=CHECK_IN,
        check_out=CHECK_OUT,
        adults=2,
        budget_total_inr=30000,
    )


async def test_complete_query_does_not_pause(fakes: Fakes) -> None:
    calls, spec = fakes
    spec["value"] = full_spec()
    run = await start_trip("full query")
    assert run["status"] == "done"
    assert run["stay_candidates"] == [LISTING]
    assert run["places"] == [PLACE]
    assert calls["search"][0]["max_price_per_night"] == 10000
    assert calls["estimate"] == []
    assert calls["prices"] == []


async def test_missing_fields_pause_the_graph(fakes: Fakes) -> None:
    calls, _ = fakes
    run = await start_trip("Goa trip")
    assert run["status"] == "needs_input"
    assert run["field"] == "check_in"
    assert run["answered"] == 0
    assert run["missing_fields"] == [
        "check_in",
        "check_out",
        "adults",
        "budget_total_inr",
    ]
    assert calls["search"] == []


async def test_questions_come_one_at_a_time_in_order(fakes: Fakes) -> None:
    _, asked = await answer_all(await start_trip("Goa trip"))
    assert asked == ["check_in", "check_out", "adults", "budget_total_inr"]


async def test_each_answer_moves_to_the_next_question(fakes: Fakes) -> None:
    first = await start_trip("Goa trip")
    run = await resume_trip(first["thread_id"], {"check_in": ANSWERS["check_in"]})
    assert run["field"] == "check_out"
    assert run["answered"] == 1
    assert run["error"] is None


async def test_resume_finishes_and_calls_llm_once(fakes: Fakes) -> None:
    calls, _ = fakes
    run, _ = await answer_all(await start_trip("Goa trip"))
    assert run["status"] == "done"
    assert run["destination"] == "Goa"
    assert calls["extract"] == 1
    assert len(calls["prices"]) == 1
    assert calls["estimate"] == []
    assert calls["search"][0]["adults"] == 2
    assert calls["places"] == [("Goa", ["beach"])]


async def test_searches_run_in_parallel(fakes: Fakes) -> None:
    calls, spec = fakes
    spec["value"] = full_spec()
    await start_trip("full query")
    assert calls["overlap"] is True


async def test_blank_answer_asks_the_same_question_again(fakes: Fakes) -> None:
    first = await start_trip("Goa trip")
    run = await resume_trip(first["thread_id"], {"check_in": ""})
    assert run["status"] == "needs_input"
    assert run["field"] == "check_in"
    assert run["error"] == "Please answer this question."


async def test_invalid_answer_asks_the_same_question_again(fakes: Fakes) -> None:
    first = await start_trip("Goa trip")
    run = await resume_trip(first["thread_id"], {"check_in": CHECK_IN.isoformat()})
    run = await resume_trip(run["thread_id"], {"check_out": CHECK_IN.isoformat()})
    assert run["status"] == "needs_input"
    assert run["field"] == "check_out"
    assert run["answered"] == 1
    assert "after the check-in" in run["error"]


def budget_spec() -> TripSpec:
    return TripSpec(destination="Goa", check_in=CHECK_IN, check_out=CHECK_OUT, adults=2)


async def test_budget_question_offers_live_airbnb_prices(fakes: Fakes) -> None:
    calls, spec = fakes
    spec["value"] = budget_spec()
    run = await start_trip("Goa trip")
    assert run["field"] == "budget_total_inr"
    assert [o["total_inr"] for o in run["budget_options"]] == [
        8000,
        12000,
        30000,
        90000,
    ]
    assert run["budget_source"] == "live"
    assert calls["prices"] == [
        {
            "destination": "Goa",
            "check_in": CHECK_IN,
            "check_out": CHECK_OUT,
            "adults": 2,
        }
    ]
    run = await resume_trip(run["thread_id"], {"budget_total_inr": ""})
    assert run["field"] == "budget_total_inr"
    assert len(calls["prices"]) == 1
    assert calls["estimate"] == []


async def test_too_few_live_prices_use_the_claude_estimate(fakes: Fakes) -> None:
    calls, spec = fakes
    calls["price_list"] = [5000, 7000]
    spec["value"] = budget_spec()
    run = await start_trip("Goa trip")
    assert run["budget_source"] == "estimate"
    assert [o["total_inr"] for o in run["budget_options"]] == [
        6000,
        12000,
        24000,
        48000,
    ]
    assert calls["estimate"] == ["Goa"]


async def test_failed_estimate_uses_default_rates(
    fakes: Fakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls, spec = fakes
    calls["price_list"] = []

    async def fail(destination: str) -> list[int]:
        raise graph.ExtractionError("no answer")

    monkeypatch.setattr(graph, "estimate_rates", fail)
    spec["value"] = TripSpec(
        destination="Goa", check_in=CHECK_IN, check_out=CHECK_OUT, adults=1
    )
    run = await start_trip("Goa trip")
    assert run["budget_source"] == "default"
    assert run["budget_options"][0]["total_inr"] == (
        graph.DEFAULT_NIGHTLY_RATES_INR[0] * 3
    )


def test_live_totals_pick_points_in_the_price_spread() -> None:
    assert live_totals(PRICES) == [8000, 12000, 30000, 90000]
    assert live_totals([5000] * 4) == [5000] * 4


def test_budget_options_add_the_nightly_share() -> None:
    options = budget_options([6000, 12000, 24000, 48000], 3)
    assert [o["total_inr"] for o in options] == [6000, 12000, 24000, 48000]
    assert options[0]["per_night_inr"] == 2000


def test_budget_options_round_up_and_drop_merged_tiers() -> None:
    options = budget_options([1010, 1020, 1030, 12340], 1)
    assert [o["total_inr"] for o in options] == [1500, 13000]
    assert [o["tier"] for o in options] == ["Budget", "Luxury"]


async def test_unknown_thread_is_rejected(fakes: Fakes) -> None:
    with pytest.raises(graph.UnknownTripError):
        await resume_trip("no-such-thread", {})


async def test_finished_thread_is_rejected(fakes: Fakes) -> None:
    _, spec = fakes
    spec["value"] = full_spec()
    run = await start_trip("full query")
    with pytest.raises(graph.UnknownTripError):
        await resume_trip(run["thread_id"], {})


async def test_finished_trip_leaves_no_checkpoints(fakes: Fakes) -> None:
    _, spec = fakes
    spec["value"] = full_spec()
    run = await start_trip(SECRET_QUERY)
    config = {"configurable": {"thread_id": run["thread_id"]}}
    assert (await graph.GRAPH.aget_state(config)).values == {}


async def test_expired_paused_trip_is_forgotten(
    fakes: Fakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = await start_trip("Goa trip")
    monkeypatch.setattr(graph, "PAUSED_TRIP_TTL_SECONDS", -1)
    await start_trip("Goa trip")
    with pytest.raises(graph.UnknownTripError):
        await resume_trip(first["thread_id"], ANSWERS)


async def test_events_cover_every_step_and_hide_the_query(fakes: Fakes) -> None:
    queue = hub.subscribe()
    try:
        await answer_all(await start_trip(SECRET_QUERY))
    finally:
        hub.unsubscribe(queue)
    events = [queue.get_nowait() for _ in range(queue.qsize())]
    kinds = [event["kind"] for event in events]
    for kind in (
        "run_start",
        "node_start",
        "node_end",
        "paused",
        "mcp_start",
        "mcp_end",
    ):
        assert kind in kinds
    assert kinds[-1] == "run_end"
    assert {e["server"] for e in events if e["kind"] == "mcp_end"} == {
        "airbnb",
        "tavily",
    }
    assert SECRET_QUERY not in json.dumps(events, default=str)
    assert "XXXXX" not in json.dumps(events, default=str)


async def test_failed_run_publishes_failure_and_forgets_trip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail(query: str) -> TripSpec:
        raise graph.ExtractionError("no key")

    monkeypatch.setattr(graph, "extract_trip", fail)
    queue = hub.subscribe()
    try:
        with pytest.raises(graph.ExtractionError):
            await start_trip("Goa")
    finally:
        hub.unsubscribe(queue)
    events = [queue.get_nowait() for _ in range(queue.qsize())]
    assert events[-1]["kind"] == "run_failed"


def test_check_spec_rejects_past_date_and_bad_numbers() -> None:
    spec = TripSpec(
        destination=" Goa ",
        check_in=TODAY - timedelta(days=1),
        check_out=CHECK_OUT,
        adults=99,
        budget_total_inr=-1,
    )
    fields, missing, error = check_spec(spec, TODAY)
    assert fields["destination"] == "Goa"
    assert missing == ["check_in", "adults", "budget_total_inr"]
    assert error is not None


def test_check_spec_limits_interests_and_does_not_require_them() -> None:
    spec = TripSpec(interests=["  beach ", "", "x" * 99, "a", "b", "c", "d"])
    fields, missing, _ = check_spec(spec, TODAY)
    assert fields["interests"][0] == "beach"
    assert len(fields["interests"]) == 4
    assert len(fields["interests"][1]) == graph.MAX_INTEREST_CHARS
    assert "interests" not in missing


def test_parse_answers_treats_blank_as_no_answer() -> None:
    parsed, error = parse_answers({"adults": "", "destination": " Goa "})
    assert parsed == {"destination": "Goa"}
    assert error is None


def test_parse_answers_keeps_valid_values_after_a_bad_value() -> None:
    parsed, error = parse_answers({"check_in": "soon", "adults": "2"})
    assert parsed == {"adults": 2}
    assert "check_in" in error


async def test_extract_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(graph.ExtractionError, match="ANTHROPIC_API_KEY"):
        await graph.extract_trip("Goa")


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

    monkeypatch.setattr(graph.anthropic, "AsyncAnthropic", build)


async def test_extract_sends_haiku_adaptive_thinking_and_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: dict[str, Any] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.update(json.loads(request.content))
        return httpx2.Response(200, json=_message('{"destination": "Goa"}'))

    _fake_client(monkeypatch, handler)
    spec = await graph.extract_trip("Goa trip")
    assert spec.destination == "Goa"
    assert sent["model"] == "claude-haiku-5-5"
    assert sent["thinking"] == {"type": "adaptive"}
    assert sent["output_config"]["effort"] == "medium"
    assert sent["output_config"]["format"]["type"] == "json_schema"
    assert "budget_tokens" not in sent["thinking"]


async def test_extract_rejects_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    body = {**_message("", "refusal"), "content": []}
    _fake_client(monkeypatch, lambda r: httpx2.Response(200, json=body))
    with pytest.raises(graph.ExtractionError, match="refusal"):
        await graph.extract_trip("Goa trip")


async def test_extract_rejects_truncated_json(monkeypatch: pytest.MonkeyPatch) -> None:
    body = _message('{"destination": "Go', "max_tokens")
    _fake_client(monkeypatch, lambda r: httpx2.Response(200, json=body))
    with pytest.raises(graph.ExtractionError, match="invalid"):
        await graph.extract_trip("Goa trip")


async def test_extract_reports_bad_key(monkeypatch: pytest.MonkeyPatch) -> None:
    body = {
        "type": "error",
        "error": {"type": "authentication_error", "message": "bad"},
    }
    _fake_client(monkeypatch, lambda r: httpx2.Response(401, json=body))
    with pytest.raises(graph.ExtractionError, match="API key"):
        await graph.extract_trip("Goa trip")


def _rates_message(**rates: int) -> dict[str, Any]:
    return _message(json.dumps(rates))


async def test_estimate_sends_destination_with_low_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: dict[str, Any] = {}
    reply = _rates_message(budget=1000, mid_range=2000, premium=4000, luxury=8000)

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.update(json.loads(request.content))
        return httpx2.Response(200, json=reply)

    _fake_client(monkeypatch, handler)
    assert await graph.estimate_rates("Goa") == RATES
    assert sent["output_config"]["effort"] == "low"
    assert sent["messages"] == [{"role": "user", "content": "Goa"}]


@pytest.mark.parametrize(
    "rates",
    [
        {"budget": 3000, "mid_range": 2000, "premium": 4000, "luxury": 8000},
        {"budget": 0, "mid_range": 2000, "premium": 4000, "luxury": 8000},
        {"budget": 1000, "mid_range": 2000, "premium": 4000, "luxury": 900000},
    ],
)
async def test_estimate_rejects_unusable_prices(
    monkeypatch: pytest.MonkeyPatch, rates: dict[str, int]
) -> None:
    body = _rates_message(**rates)
    _fake_client(monkeypatch, lambda r: httpx2.Response(200, json=body))
    with pytest.raises(graph.ExtractionError):
        await graph.estimate_rates("Goa")
