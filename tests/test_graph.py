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
from app.graph import TripSpec, check_spec, parse_answers, resume_trip, start_trip

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
SECRET_QUERY = "Goa trip, my PAN placeholder is XXXXX"

Fakes = tuple[dict[str, Any], dict[str, TripSpec]]


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> Fakes:
    calls: dict[str, Any] = {
        "extract": 0,
        "search": [],
        "places": [],
        "concurrent": 0,
        "prices": [],
        "nightly": [3000, 4000, 5000, 6000, 8000],
    }
    spec = {"value": TripSpec(destination="Goa", interests=["beach"])}

    async def fake_extract(query: str) -> TripSpec:
        calls["extract"] += 1
        return spec["value"]

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

    async def fake_prices(*args: Any) -> dict[str, Any]:
        calls["prices"].append(args)
        return {"prices": calls["nightly"]}

    monkeypatch.setattr(graph, "extract_trip", fake_extract)
    monkeypatch.setattr(graph, "fetch_nightly_prices", fake_prices)
    monkeypatch.setattr(graph, "search_stays", fake_search)
    monkeypatch.setattr(graph, "search_places", fake_places)
    return calls, spec


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


async def test_missing_fields_pause_the_graph(fakes: Fakes) -> None:
    calls, _ = fakes
    run = await start_trip("Goa trip")
    assert run["status"] == "needs_input"
    # Only the first question is asked. Three more wait behind it.
    assert run["missing_fields"] == ["check_in"]
    assert run["remaining"] == 4
    assert "budget_options" not in run
    assert calls["search"] == []
    assert calls["prices"] == []


async def test_questions_come_one_at_a_time_and_budget_is_priced_last(
    fakes: Fakes,
) -> None:
    calls, _ = fakes
    run = await start_trip("Goa trip")
    for field, answer in (
        ("check_in", CHECK_IN.isoformat()),
        ("check_out", (CHECK_IN + timedelta(days=5)).isoformat()),
        ("adults", "4"),
    ):
        assert run["missing_fields"] == [field]
        assert calls["prices"] == []
        run = await resume_trip(run["thread_id"], {field: answer})
    assert run["missing_fields"] == ["budget_total_inr"]
    assert run["remaining"] == 1
    assert run["budget_basis"] == "live"
    # The lookup used the destination, the dates and the adults of this trip.
    assert calls["prices"] == [("Goa", CHECK_IN, CHECK_IN + timedelta(days=5), 4)]
    # Median nightly price 5000 for 5 nights.
    assert [o["value"] for o in run["budget_options"]][1] == "25000"
    done = await resume_trip(run["thread_id"], {"budget_total_inr": "25000"})
    assert done["status"] == "done"
    assert len(calls["prices"]) == 1
    assert calls["search"][0]["max_price_per_night"] == 5000


async def test_rejected_budget_asks_again_without_a_second_lookup(
    fakes: Fakes,
) -> None:
    calls, spec = fakes
    spec["value"] = TripSpec(
        destination="Goa", check_in=CHECK_IN, check_out=CHECK_OUT, adults=2
    )
    run = await start_trip("Goa trip")
    assert run["missing_fields"] == ["budget_total_inr"]
    again = await resume_trip(run["thread_id"], {"budget_total_inr": "0"})
    assert again["missing_fields"] == ["budget_total_inr"]
    assert "more than zero" in again["error"]
    assert again["budget_options"] == run["budget_options"]
    assert len(calls["prices"]) == 1


async def test_budget_is_an_estimate_when_airbnb_gives_no_prices(
    fakes: Fakes,
) -> None:
    calls, spec = fakes
    calls["nightly"] = []
    spec["value"] = TripSpec(
        destination="Goa", check_in=CHECK_IN, check_out=CHECK_OUT, adults=2
    )
    run = await start_trip("Goa trip")
    assert run["budget_basis"] == "estimate"
    assert run["budget_options"]


async def test_a_stated_budget_needs_no_price_lookup(fakes: Fakes) -> None:
    calls, spec = fakes
    spec["value"] = full_spec()
    await start_trip("full query")
    assert calls["prices"] == []


async def test_resume_finishes_and_calls_llm_once(fakes: Fakes) -> None:
    calls, _ = fakes
    first = await start_trip("Goa trip")
    run = await resume_trip(first["thread_id"], ANSWERS)
    assert run["status"] == "done"
    assert run["destination"] == "Goa"
    assert calls["extract"] == 1
    assert calls["search"][0]["adults"] == 2
    assert calls["places"] == [("Goa", ["beach"])]


async def test_searches_run_in_parallel(fakes: Fakes) -> None:
    calls, spec = fakes
    spec["value"] = full_spec()
    await start_trip("full query")
    assert calls["overlap"] is True


async def test_blank_answers_pause_again_with_message(fakes: Fakes) -> None:
    first = await start_trip("Goa trip")
    run = await resume_trip(first["thread_id"], {"adults": "2"})
    assert run["status"] == "needs_input"
    assert "adults" not in run["missing_fields"]
    assert run["missing_fields"] == ["check_in"]
    assert run["error"] == "Please answer the question."


async def test_invalid_answers_pause_again_with_error(fakes: Fakes) -> None:
    first = await start_trip("Goa trip")
    run = await resume_trip(
        first["thread_id"],
        {
            **ANSWERS,
            "check_in": CHECK_OUT.isoformat(),
            "check_out": CHECK_IN.isoformat(),
        },
    )
    assert run["status"] == "needs_input"
    assert run["missing_fields"] == ["check_out"]
    assert "after the check-in" in run["error"]


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
        first = await start_trip(SECRET_QUERY)
        await resume_trip(first["thread_id"], ANSWERS)
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
