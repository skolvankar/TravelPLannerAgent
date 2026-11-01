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
# The first amount is the price to pay. A discount label adds "originally" after it.
STAY_TOTAL = re.compile(r"₹\s*([\d,]+)\s+for\s+\d+\s+nights?")


def _price_label(raw: dict[str, Any]) -> Any:
    return ((raw.get("structuredDisplayPrice") or {}).get("primaryLine") or {}).get(
        "accessibilityLabel"
    )


def parse_stay_total(raw: dict[str, Any]) -> int | None:
    """Return the rupee total of one listing for the whole stay, if the label has one."""
    label = _price_label(raw)
    match = STAY_TOTAL.search(label) if isinstance(label, str) else None
    if match is None:
        return None
    return int(match.group(1).replace(",", "")) or None


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
    price = _price_label(raw)
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


async def fetch_stay_totals(
    destination: str, check_in: date, check_out: date, adults: int
) -> dict[str, list[int]]:
    """Read stay totals with no price limit. A failure returns none, never sample data."""
    arguments = {
        "location": destination,
        "checkin": check_in.isoformat(),
        "checkout": check_out.isoformat(),
        "adults": adults,
    }
    logger.info(f"MCP airbnb_search for prices | arguments={arguments}")
    try:
        payload = await call_airbnb(arguments)
        if "error" in payload:
            raise RuntimeError(payload["error"])
        found = (parse_stay_total(raw) for raw in payload.get("searchResults") or [])
        totals = [total for total in found if total]
    except MCP_FAILURES as e:
        # The sample prices are from Goa, so they cannot price another destination.
        logger.warning(f"FAILED: airbnb_search for prices | reason={e}")
        return {"totals": []}
    logger.success(f"MCP airbnb_search for prices | totals={len(totals)}")
    return {"totals": totals}
