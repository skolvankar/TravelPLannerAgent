"""Browser test of the page, with fake LLM and fake MCP searches."""

import socket
import threading
import time
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import pytest
import uvicorn
from playwright.sync_api import Page, expect, sync_playwright

from app import graph
from app.graph import TripSpec
from app.server import HTTP_MIDDLEWARE, mcp

CHECK_IN = date.today() + timedelta(days=30)
CHECK_OUT = CHECK_IN + timedelta(days=3)
HOSTILE_NAME = "<img src=x onerror=window.hacked=1>"


async def fake_extract(query: str) -> TripSpec:
    return TripSpec(destination="Goa", interests=["beach"])


async def fake_rates(destination: str) -> dict[str, int]:
    return {"budget": 1000, "mid_range": 2000, "premium": 4000, "luxury": 8000}


async def fake_stays(**kwargs: Any) -> dict[str, Any]:
    listing = {
        "name": HOSTILE_NAME,
        "url": "https://x.test/stay",
        "price": "₹1,000 for 3 nights",
        "rating": "5.0",
        "details": "1 bed",
    }
    return {"listings": [listing], "source": "live", "search_url": "https://x.test/s"}


async def fake_places(destination: str, interests: list[str]) -> dict[str, Any]:
    place = {"title": "Palolem", "url": "https://x.test/place", "summary": "Sand"}
    return {"places": [place], "available": True}


@pytest.fixture(scope="module")
def server_url() -> Iterator[str]:
    patch = pytest.MonkeyPatch()
    patch.setattr(graph, "extract_trip", fake_extract)
    patch.setattr(graph, "estimate_rates", fake_rates)
    patch.setattr(graph, "search_stays", fake_stays)
    patch.setattr(graph, "search_places", fake_places)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    config = uvicorn.Config(
        mcp.http_app(
            middleware=HTTP_MIDDLEWARE, stateless_http=True, json_response=True
        ),
        host="127.0.0.1",
        port=port,
        log_level="warning",
        timeout_graceful_shutdown=1,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)
    patch.undo()


@pytest.fixture
def page() -> Iterator[Page]:
    # Not the pytest-playwright plugin: its open event loop breaks later async tests.
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        yield browser.new_page()
        browser.close()


def test_form_flow_and_live_sidebar(page: Page, server_url: str) -> None:
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(server_url)

    # The real LangGraph diagram draws, and the event stream is open.
    expect(page.locator("#graph-diagram svg")).to_be_visible()
    expect(page.locator('.node[id*="flowchart-intake-"]')).to_be_visible()

    page.fill("#query", "Beach trip to Goa")
    page.click("#send")

    # The graph pauses, the form asks one question, and the sidebar shows the pause.
    expect(page.locator("#graph-status")).to_contain_text(
        "Paused: waiting for check_in"
    )
    expect(page.locator('.node.active[id*="flowchart-intake-"]')).to_be_visible()
    expect(page.locator("#view")).to_contain_text("3 more questions after this.")
    expect(page.locator("#check_out")).to_have_count(0)
    page.fill("#check_in", CHECK_IN.isoformat())
    page.click("text=Next")

    # An invalid date asks the same question again with the error.
    page.fill("#check_out", CHECK_IN.isoformat())
    page.click("text=Next")
    expect(page.locator(".error")).to_contain_text("after the check-in")
    page.fill("#check_out", CHECK_OUT.isoformat())
    page.click("text=Next")

    page.fill("#adults", "6")
    page.click("text=Next")

    # 6 adults need 3 rooms for 3 nights, so Mid-range is 2,000 x 3 x 3.
    expect(page.locator("#budget_total_inr-18000")).to_be_attached()
    expect(page.locator("#view")).to_contain_text("Mid-range · ₹18,000 (3 rooms")
    expect(page.locator("#adults")).to_have_count(0)
    page.check("#budget_total_inr-18000")
    page.click("text=Search stays")

    # Results and sidebar finish. Hostile listing text stays as plain text.
    expect(page.locator("#graph-status")).to_have_text("Complete")
    expect(page.locator("#view")).to_contain_text("Things to do in Goa")
    expect(page.locator("#view a").first).to_have_text(HOSTILE_NAME)
    assert page.evaluate("window.hacked") is None
    steps = page.locator("#graph-steps")
    expect(steps).to_contain_text("MCP call finished: airbnb")
    expect(steps).to_contain_text("MCP call finished: tavily")
    expect(steps).not_to_contain_text("Beach trip to Goa")
    assert errors == []
