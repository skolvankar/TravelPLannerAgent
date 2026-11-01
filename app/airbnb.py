"""FastMCP client for the Airbnb MCP server, with a labelled sample fallback."""

import json
import re
from datetime import date
from typing import Any

from loguru import logger

from app.config import MAX_LISTINGS, SAMPLE_LISTINGS_PATH
from app.mcp_client import MCP_FAILURES, is_https_url, open_client

SOURCE_LIVE = "live"
SOURCE_SAMPLE = "sample"
PRICE_PATTERN = re.compile(r"₹\s*([\d,]+)(?:\s+for\s+(\d+)\s+nights?)?")


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


def parse_nightly_price(label: str | None) -> int | None:
    """Turn a label such as '₹17,565 for 3 nights' into rupees per night."""
    match = PRICE_PATTERN.search(label or "")
    if not match:
        return None
    amount = int(match.group(1).replace(",", ""))
    if match.group(2):
        return amount // int(match.group(2)) or None
    return amount if "night" in (label or "") else None


def parse_nightly_prices(payload: dict[str, Any]) -> list[int]:
    """Read the nightly price of every result. Unlike parse_search, this is not capped."""
    prices = (
        parse_nightly_price(
            ((raw.get("structuredDisplayPrice") or {}).get("primaryLine") or {}).get(
                "accessibilityLabel"
            )
        )
        for raw in payload.get("searchResults") or []
    )
    return [price for price in prices if price]


def load_sample() -> list[dict[str, Any]]:
    return json.loads(SAMPLE_LISTINGS_PATH.read_text(encoding="utf-8"))


async def call_airbnb(arguments: dict[str, Any]) -> dict[str, Any]:
    """Call airbnb_search over MCP. Return the payload of the tool result."""
    async with open_client("airbnb") as client:
        result = await client.call_tool(
            "airbnb_search", arguments, raise_on_error=False
        )
    return json.loads(result.content[0].text)


async def fetch_nightly_prices(
    destination: str, check_in: date, check_out: date, adults: int
) -> dict[str, Any]:
    """Search without a price limit and return the live nightly prices.

    A failure returns no prices, so the caller can fall back to an estimate.
    Sample data is never used here, because it is for Goa only.
    """
    arguments = {
        "location": destination,
        "checkin": check_in.isoformat(),
        "checkout": check_out.isoformat(),
        "adults": adults,
    }
    logger.info(f"MCP airbnb_search | price_lookup arguments={arguments}")
    try:
        payload = await call_airbnb(arguments)
        if "error" in payload:
            raise RuntimeError(payload["error"])
        prices = parse_nightly_prices(payload)
    except MCP_FAILURES as e:
        logger.warning(f"FAILED: airbnb price lookup | reason={e}")
        return {"prices": []}
    logger.success(f"MCP airbnb_search | price_lookup prices={len(prices)}")
    return {"prices": prices}


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
    logger.info(f"MCP airbnb_search | arguments={arguments}")
    try:
        payload = await call_airbnb(arguments)
        if "error" in payload:
            raise RuntimeError(payload["error"])
        listings = parse_search(payload)
    except MCP_FAILURES as e:
        # The demo must continue when the scraper breaks. The UI labels the data.
        logger.warning(f"FAILED: airbnb_search | reason={e} | using sample data")
        return {"listings": load_sample(), "source": SOURCE_SAMPLE}
    logger.success(f"MCP airbnb_search | listings={len(listings)}")
    return {"listings": listings, "source": SOURCE_LIVE}
