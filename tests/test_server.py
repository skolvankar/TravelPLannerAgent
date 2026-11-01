from typing import Any

import pytest
from fastmcp import Client
from starlette.testclient import TestClient

from app import graph
from app.graph import ExtractionError, TripSpec
from app.server import HTTP_MIDDLEWARE, mcp

LOCAL_URL = "http://127.0.0.1:8000"


async def call(client: Client, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = await client.call_tool(name, arguments)
    return result.structured_content


@pytest.fixture
def fake_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_extract(query: str) -> TripSpec:
        return TripSpec(destination="Goa")

    monkeypatch.setattr(graph, "extract_trip", fake_extract)


def http_client() -> TestClient:
    return TestClient(mcp.http_app(middleware=HTTP_MIDDLEWARE), base_url=LOCAL_URL)


async def test_plan_stay_returns_prefab_form(fake_agent: None) -> None:
    async with Client(mcp) as client:
        tree = await call(client, "plan_stay", {"query": "Goa trip"})
    assert tree["$prefab"]
    assert "DatePicker" in str(tree["view"])
    assert "RadioGroup" not in str(tree["view"])


async def test_empty_query_returns_structured_error() -> None:
    async with Client(mcp) as client:
        tree = await call(client, "plan_stay", {"query": "   "})
    assert tree["state"]["code"] == "VALIDATION_ERROR"


async def test_extraction_failure_returns_structured_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail(query: str) -> TripSpec:
        raise ExtractionError("no key")

    monkeypatch.setattr(graph, "extract_trip", fail)
    async with Client(mcp) as client:
        tree = await call(client, "plan_stay", {"query": "Goa"})
    assert tree["state"] == {
        "status": "error",
        "code": "EXTRACTION_ERROR",
        "detail": "no key",
    }


async def test_unknown_thread_returns_structured_error() -> None:
    async with Client(mcp) as client:
        tree = await call(client, "submit_trip_details", {"thread_id": "missing"})
    assert tree["state"]["code"] == "UNKNOWN_TRIP"


@pytest.mark.parametrize(
    ("path", "marker"),
    [
        ("/", "Travel Planner"),
        ("/static/style.css", ".radio-group"),
        ("/static/app.js", "callTool"),
        ("/static/graph_panel.js", "EventSource"),
        ("/graph", "intake -.-> estimate_budget"),
    ],
)
def test_page_files_are_served(path: str, marker: str) -> None:
    with http_client() as client:
        response = client.get(path)
    assert response.status_code == 200
    assert marker in response.text


def test_static_route_rejects_other_files() -> None:
    with http_client() as client:
        assert client.get("/static/../config.py").status_code == 404
        assert client.get("/static/secret.txt").status_code == 404


@pytest.mark.parametrize("path", ["/", "/graph", "/mcp"])
def test_foreign_host_is_rejected(path: str) -> None:
    with http_client() as client:
        response = client.get(path, headers={"Host": "evil.example"})
    assert response.status_code == 400
