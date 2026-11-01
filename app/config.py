"""Project settings. One edit here changes the model or the Airbnb server."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "app" / "static"
SAMPLE_LISTINGS_PATH = ROOT / "app" / "fixtures" / "airbnb_sample.json"

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
# The vendored Airbnb server is 0.3.0 with one patch: AIRBNB_BASE_URL replaces the
# hardcoded airbnb.com, which returns a stub page to Indian IP addresses.
MCP_CONFIG_PATH = ROOT / "mcp_client.json"
MCP_TIMEOUT_SECONDS = 60

MAX_QUERY_CHARS = 2000
MAX_LISTINGS = 5
MAX_PLACES = 5
MAX_PLACE_TEXT_CHARS = 300
MAX_INTERESTS = 5
MAX_INTEREST_CHARS = 40
PAUSED_TRIP_TTL_SECONDS = 3600

# Budget options = nightly room rate x rooms x nights x tier multiplier.
# Rough mid-range Airbnb rates for one room for two adults. Edit freely.
DESTINATION_NIGHTLY_INR = {
    "goa": 4500,
    "mumbai": 6000,
    "delhi": 4500,
    "bengaluru": 4000,
    "bangalore": 4000,
    "jaipur": 3500,
    "udaipur": 4500,
    "manali": 3000,
    "shimla": 3000,
    "rishikesh": 2500,
    "kerala": 4000,
    "munnar": 3500,
    "ooty": 3000,
    "pondicherry": 3500,
    "varanasi": 2500,
}
DEFAULT_NIGHTLY_INR = 3500
ADULTS_PER_ROOM = 2
BUDGET_TIERS = (
    ("Economy", 0.6),
    ("Standard", 1.0),
    ("Comfort", 1.6),
    ("Luxury", 2.5),
)
