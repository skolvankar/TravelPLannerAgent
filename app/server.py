"""Travel Agent FastMCP server. It holds the agent and serves the browser page."""

import asyncio
import json
import sys
from collections.abc import AsyncIterator
from typing import Any

from dotenv import load_dotenv
from fastmcp import FastMCP
from loguru import logger
from prefab_ui import PrefabApp
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, PlainTextResponse, StreamingResponse

from app.config import HOST, MAX_QUERY_CHARS, PORT, STATIC_DIR
from app.events import hub
from app.graph import (
    ExtractionError,
    UnknownTripError,
    graph_diagram,
    resume_trip,
    start_trip,
)
from app.ui import build_error, build_form, build_results

mcp = FastMCP("Travel Agent")

KEEP_ALIVE_SECONDS = 15
STATIC_FILES = {
    "style.css": STATIC_DIR / "style.css",
    "app.js": STATIC_DIR / "app.js",
    "graph_panel.js": STATIC_DIR / "graph_panel.js",
    "vendor/mermaid.min.js": STATIC_DIR / "vendor" / "mermaid.min.js",
}
# A DNS rebinding website sends its own name as the Host. This list rejects it.
HTTP_MIDDLEWARE = [
    Middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
]


def _view_for(run: dict[str, Any]) -> PrefabApp:
    if run["status"] == "needs_input":
        return build_form(
            run["thread_id"],
            run["field"],
            run["error"],
            answered=run["answered"],
            remaining=len(run["missing_fields"]),
            budget_options=run.get("budget_options"),
            budget_source=run.get("budget_source"),
        )
    return build_results(
        run["destination"],
        run["stay_candidates"],
        run["stay_source"],
        run["places"],
        run["places_available"],
    )


@mcp.tool(app=True)
async def plan_stay(query: str) -> PrefabApp:
    """Start a stay search from a customer message. Return a form or the results."""
    logger.info(f"TOOL plan_stay | query_chars={len(query)}")
    query = query.strip()
    if not query or len(query) > MAX_QUERY_CHARS:
        detail = f"Enter a trip request of 1 to {MAX_QUERY_CHARS} characters."
        logger.error(f"FAILED: plan_stay | reason={detail}")
        return build_error("VALIDATION_ERROR", detail)
    try:
        run = await start_trip(query)
    except ExtractionError as e:
        logger.error(f"FAILED: plan_stay | reason={e}")
        return build_error("EXTRACTION_ERROR", str(e))
    logger.success(f"TOOL plan_stay | status={run['status']}")
    return _view_for(run)


@mcp.tool(app=True)
async def submit_trip_details(
    thread_id: str,
    destination: str | None = None,
    check_in: str | None = None,
    check_out: str | None = None,
    adults: str | None = None,
    budget_total_inr: str | None = None,
) -> PrefabApp:
    """Resume a paused trip with the form answers. Return a form or the results."""
    logger.info(f"TOOL submit_trip_details | thread_id={thread_id}")
    answers = {
        "destination": destination,
        "check_in": check_in,
        "check_out": check_out,
        "adults": adults,
        "budget_total_inr": budget_total_inr,
    }
    try:
        run = await resume_trip(thread_id, answers)
    except UnknownTripError:
        detail = "This trip has expired or is complete. Send your request again."
        logger.error(f"FAILED: submit_trip_details | reason={detail}")
        return build_error("UNKNOWN_TRIP", detail)
    logger.success(f"TOOL submit_trip_details | status={run['status']}")
    return _view_for(run)


@mcp.custom_route("/", methods=["GET"])
async def index(request: Request) -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@mcp.custom_route("/static/{name:path}", methods=["GET"])
async def static_file(request: Request) -> FileResponse | PlainTextResponse:
    path = STATIC_FILES.get(request.path_params["name"])
    if path is None:
        return PlainTextResponse("Not found", status_code=404)
    return FileResponse(path)


@mcp.custom_route("/graph", methods=["GET"])
async def graph_text(request: Request) -> PlainTextResponse:
    logger.info("GET /graph")
    return PlainTextResponse(graph_diagram())


async def _event_stream(queue: asyncio.Queue[dict[str, Any]]) -> AsyncIterator[str]:
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), KEEP_ALIVE_SECONDS)
            except TimeoutError:
                yield ": keep-alive\n\n"
                continue
            yield f"data: {json.dumps(event, default=str)}\n\n"
    finally:
        hub.unsubscribe(queue)


@mcp.custom_route("/events", methods=["GET"])
async def events(request: Request) -> StreamingResponse:
    logger.info("GET /events")
    return StreamingResponse(
        _event_stream(hub.subscribe()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


def main() -> None:
    load_dotenv()
    logger.remove()
    logger.add(sys.stderr, level="DEBUG")
    logger.add("logs/app.log", rotation="10 MB", retention="7 days", level="DEBUG")
    logger.info(f"Open http://{HOST}:{PORT}/")
    mcp.run(
        transport="http",
        host=HOST,
        port=PORT,
        stateless_http=True,
        json_response=True,
        show_banner=False,
        middleware=HTTP_MIDDLEWARE,
        # An open /events stream must not hold up a server stop.
        uvicorn_config={"timeout_graceful_shutdown": 1},
    )


if __name__ == "__main__":
    main()
