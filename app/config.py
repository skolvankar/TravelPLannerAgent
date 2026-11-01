"""Project settings. One edit here changes the model or the Airbnb server."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "app" / "static"
SAMPLE_LISTINGS_PATH = ROOT / "app" / "fixtures" / "airbnb_sample.json"
# The sample listings are from this place, so only a trip there shows them.
SAMPLE_DESTINATION = "Goa"
# The results link to an Airbnb search on this site when live stays are missing.
AIRBNB_SEARCH_BASE_URL = "https://www.airbnb.co.in"

HOST = "127.0.0.1"
PORT = 8000

# Haiku 5.5 because the only LLM step is field extraction.
# This model rejects budget_tokens, so adaptive thinking plus effort sets the
# thinking depth, and max_tokens is the hard limit for one response.
LLM_MODEL = "claude-haiku-5-5"
LLM_THINKING = {"type": "adaptive"}
LLM_EFFORT = "medium"
LLM_MAX_TOKENS = 16000

# mcp_client.json holds the MCP servers. It uses ${NAME} for secrets, never values.
# Airbnb runs the published @openbnb/mcp-server-airbnb through npx. It hardcodes
# airbnb.com, which returns a stub page to Indian IP addresses, so the live search
# can fall back to the sample listings.
MCP_CONFIG_PATH = ROOT / "mcp_client.json"
MCP_TIMEOUT_SECONDS = 60

MAX_QUERY_CHARS = 2000
MAX_LISTINGS = 5
MAX_PLACES = 5
MAX_PLACE_TEXT_CHARS = 300
MAX_INTERESTS = 5
MAX_INTEREST_CHARS = 40
PAUSED_TRIP_TTL_SECONDS = 3600

# Budget choices: total = nightly rate for one room x rooms x nights, where one room
# holds ADULTS_PER_ROOM adults. The LLM estimates the rates for the destination.
# DEFAULT_NIGHTLY_RATES replaces an estimate that fails or is outside the limits.
ADULTS_PER_ROOM = 2
BUDGET_ROUNDING_INR = 500
MIN_NIGHTLY_RATE_INR = 500
MAX_NIGHTLY_RATE_INR = 200000
DEFAULT_NIGHTLY_RATES = {
    "budget": 1500,
    "mid_range": 3500,
    "premium": 7000,
    "luxury": 15000,
}
