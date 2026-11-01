"""FastMCP client for the Airbnb MCP server, with a labelled sample fallback."""

import json
import re
from datetime import date
from typing import Any
from urllib.parse import quote, urlencode

from loguru import logger

from app.config import (
    AIRBNB_SEARCH_BASE_URL,
    MAX_LISTINGS,
    SAMPLE_DESTINATION,
    SAMPLE_LISTINGS_PATH,
)
from app.mcp_client import MCP_FAILURES, is_https_url, open_client

SOURCE_LIVE = "live"
SOURCE_SAMPLE = "sample"
SOURCE_UNAVAILABLE = "unavailable"


def search_link(destination: str, check_in: date, check_out: date, adults: int) -> str:
    """Build an Airbnb search link, so the customer can search the site directly."""
    query = urlencode(
        {
            "checkin": check_in.isoformat(),
            "checkout": check_out.isoformat(),
            "adults": adults,
        }
    )
    path = quote(destination, safe="")
    return f"{AIRBNB_SEARCH_BASE_URL}/s/{path}/homes?{query}"


def is_sample_destination(destination: str) -> bool:
    pattern = rf"\b{re.escape(SAMPLE_DESTINATION)}\b"
    return re.search(pattern, destination, re.IGNORECASE) is not None


def parse_listing(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Keep the display fields of one listing. Reject a listing with no safe link."""
    url = raw.get("url")
    if not is_https_url(url):
        logger.warning(f"ACTION: parse_listing | rejected_id={raw.get('id')}")
        return None
    description = (raw.get("demandStayListing") or {}).get("description") or {}
    name = (description.get("name") or {}).get(
        "localizedStringWithTranslationPreference"
    )
    price = ((raw.get("structuredDisplayPrice") or {}).get("primaryLine") or {}).get(
        "accessibilityLabel"
    )
    return {
        "id": raw.get("id"),
        "name": name or "Airbnb listing",
        "url": url,
        "price": price or "Price not shown",
        "rating": raw.get("avgRatingA11yLabel") or "No rating",
        "details": (raw.get("structuredContent") or {}).get("primaryLine") or "",
    }


def parse_search(payload: dict[str, Any]) -> list[dict[str, Any]]:
    listings = (parse_listing(raw) for raw in payload.get("searchResults") or [])
    return [listing for listing in listings if listing][:MAX_LISTINGS]


def load_sample() -> list[dict[str, Any]]:
    return json.loads(SAMPLE_LISTINGS_PATH.read_text(encoding="utf-8"))


async def call_airbnb(arguments: dict[str, Any]) -> dict[str, Any]:
    """Call airbnb_search over MCP. Return the payload of the tool result."""
    async with open_client("airbnb") as client:
        result = await client.call_tool(
            "airbnb_search", arguments, raise_on_error=False
        )
    return json.loads(result.content[0].text)


async def search_stays(
    destination: str,
    check_in: date,
    check_out: date,
    adults: int,
    max_price_per_night: int,
) -> dict[str, Any]:
    arguments = {
        "location": destination,
        "checkin": check_in.isoformat(),
        "checkout": check_out.isoformat(),
        "adults": adults,
        "maxPrice": max_price_per_night,
    }
    link = search_link(destination, check_in, check_out, adults)
    logger.info(f"MCP airbnb_search | arguments={arguments}")
    try:
        payload = await call_airbnb(arguments)
        if "error" in payload:
            raise RuntimeError(payload["error"])
        listings = parse_search(payload)
    except MCP_FAILURES as e:
        # The demo must continue when the scraper breaks. The UI labels the data.
        # Sample listings from another place would mislead, so they show only for
        # a trip to the sample destination.
        if is_sample_destination(destination):
            logger.warning(f"FAILED: airbnb_search | reason={e} | using sample data")
            return {
                "listings": load_sample(),
                "source": SOURCE_SAMPLE,
                "search_url": link,
            }
        logger.warning(f"FAILED: airbnb_search | reason={e} | no stays to show")
        return {"listings": [], "source": SOURCE_UNAVAILABLE, "search_url": link}
    logger.success(f"MCP airbnb_search | listings={len(listings)}")
    return {"listings": listings, "source": SOURCE_LIVE, "search_url": link}
