# CLAUDE.md

Minimal teaching slice of the Travel Planner PRD. It shows a FastMCP server, two external MCP servers (Airbnb and Tavily), a two-node LangGraph agent, a form that the server describes with Prefab, and a live view of each graph step.

## Run

1. Copy `.env.example` to `.env`. Add `ANTHROPIC_API_KEY` and `tavilyApiKey`.
2. Run `uv run python -m app.server`.
3. Open `http://127.0.0.1:8000/`.

Checks: `uv run black .`, `uv run ruff check .`, `uv run pytest`.

The Playwright test needs a browser. To install it, run `uv run playwright install chromium`.

## Architecture

```
Browser page (app/static)
  ├─ Main area: fetch POST /mcp, tools/call ─► FastMCP server (app/server.py)
  └─ Sidebar: GET /events (SSE), GET /graph ◄─┘
        └─► LangGraph intake and process (app/graph.py)
              ├─► Airbnb MCP over stdio (vendored server)
              └─► Tavily MCP over HTTP (remote server)
```

- `intake` calls the LLM once. It then loops to itself and pauses with `interrupt()` until no required field is missing. Each pause asks only the first missing field, and the server ignores answers for other fields.
- The budget is the last question. Before that pause, `intake` searches Airbnb with no price limit and `app/budget.py` builds the options from the stay totals. A resume runs the node from the top, so this search runs in an earlier pass and does not repeat.
- `process` uses no LLM. It calls Airbnb and Tavily in parallel.
- `mcp_client.json` holds all MCP servers. It uses `${NAME}` for secrets, never values. `app/mcp_client.py` expands the names and opens one client for each server. FastMCP does not expand `${NAME}` itself.
- `app/ui.py` builds Prefab components. The tools return them as JSON in `structuredContent`.
- `app/static/app.js` draws that JSON as native HTML. It supports only the components in `drawers`. A new component in `ui.py` needs a new drawer in `app.js`. A test checks this.
- `app/graph.py` runs the graph with `stream_mode=["tasks", "custom"]` and publishes events through `app/events.py`. Task events include the node input, which holds the customer message. Never publish `chunk["input"]`. `safe_changes` is the allow list.

## Decisions that differ from the defaults

| Topic | Decision | Why |
|---|---|---|
| Model | `claude-haiku-5-5` with adaptive thinking and `medium` effort | The user chose this model. It rejects `budget_tokens`, so effort sets the depth and `max_tokens` is the hard limit. The global file says `claude-haiku-4-5`. This file wins on model choice |
| API-first rule | No FastAPI. MCP tools and three small routes are the only interface | User-approved exception. The goal is to show MCP |
| Tavily transport | Remote HTTP with an `Authorization` header | The user chose the remote server. The PRD says `npx`. The header keeps the key out of URLs |
| Key name | `tavilyApiKey` in `.env` | The user chose this name |
| Tavily tools | `tavily_search` only | The PRD puts `tavily_extract` behind a human pause, which is out of scope |
| PRD robots rule | `--ignore-robots-txt` is on | The user approved this. The PRD says the flag stays off |
| PRD domain allow list | Not included | Minimal scope. Each result shows its source link |
| PRD scope | Two nodes only. No Laya, supervisor, Trip Rules, or planner | User-approved minimal scope |
| Sample data location | `app/fixtures/`, not `data/` or `tests/` | `data/` is protected, and the application reads this file at runtime |
| Budget options | The 25th, 50th, 75th, and 90th percentiles of live Airbnb stay totals, rounded up to ₹500. The form offers only these values | The user chose live prices over an LLM estimate or a city table |
| Budget fallback | `rooms × nightly rate × nights`, with a page note, when the search fails or returns fewer than 4 prices. The recorded Goa listings are never used | Those prices are wrong for other destinations |
| Playwright | The `playwright` package directly, not the `pytest-playwright` plugin | The plugin keeps an event loop open, which breaks the async tests that run after it |

## Vendored code

- `vendor/mcp-server-airbnb/` is `@openbnb/mcp-server-airbnb` 0.3.0 with one change on line 137 of `dist/index.js`: `const BASE_URL = process.env.AIRBNB_BASE_URL || "https://www.airbnb.com";`. Reason: `airbnb.com` returns an 873-byte stub to this network (upstream issue #60). `node_modules` is not committed. To restore it, run `npm install --omit=dev --ignore-scripts` in that folder.
- `app/static/vendor/mermaid.min.js` is Mermaid 11.17.2, so the demo needs no CDN.

## Known open issues

1. The Airbnb server parses HTML, so a site change can break it. The page then shows recorded listings with a "SAMPLE DATA" label.
2. Paused trips are in memory. A server restart loses them, and the page asks the user to send the request again. Paused trips expire after one hour.
3. The tools and routes have no authentication. The server binds to `127.0.0.1` and rejects other Host names.
4. The sample listings are from Goa on 2026-11-01. They are not results for the search of the user, and the page says so.
5. Every open tab receives the events of every trip. This is acceptable for a local single-user demo, but not for a shared server.
6. Tavily results come from any website. The text is shown as plain text, and no LLM reads it. Adding an LLM step needs a prompt injection review.
7. Budget options can change between two identical searches, because Airbnb returns a different set of 18 listings. On 2026-11-01, the Mid-range value for one Jaipur search was ₹13,000 and then ₹16,500.
8. The nightly rates of the budget fallback in `app/config.py` (₹2,000 to ₹15,000) are starting values, not market data. The fallback does not use the location, and the page says so.
9. A trip that asks for the budget makes two Airbnb searches. The budget question takes about 7 seconds to appear.

## Open code review findings (third review, one-at-a-time and budget options, 2026-11-01, not fixed, the user chose to commit)

1. `app/graph.py`: `check_spec` keeps only the error of the first missing field, so an invalid value from the customer message can disappear with no explanation.
2. `app/graph.py`: `_budget_update` never rebuilds the options, so a date that is cleared and answered again can leave stale options.
3. `app/airbnb.py`: `STAY_TOTAL` is not verified against a real one-night label. A different label makes one-night trips use the estimate.
4. `app/airbnb.py`: one malformed price label raises `ValueError`, which discards all live prices for that search.
5. `app/graph.py`: the extraction prompt says "whole-trip" budget, but the form says "whole stay" and the code treats both as a stay budget.
6. `app/airbnb.py`: trips that ask for the budget run two full Airbnb searches.
7. `app/ui.py`: `build_form` defaults to `budget_live=True` and no options, and only tests use those defaults.
8. `app/ui.py`: the form logic repeats the literal `budget_total_inr` instead of one shared name.

## Open code review findings (second review, 2026-11-01, not fixed, waiting for user approval)

1. `app/static/graph_panel.js`: the sidebar does not filter events by trip, so an older run can mix into the current run.
2. `app/graph.py`: the Anthropic call has only the 10-minute default timeout.
3. `app/graph.py`: budget and stay length have no upper limits, and the nightly limit can be 0.
4. `app/graph.py`: concurrent resume of one trip is not prevented, and a resuming trip can expire.
5. `app/graph.py`: a failed node is reported as finished in the sidebar.
6. `app/graph.py`: cancelled runs skip cleanup, so the customer message can stay in memory.
7. `app/server.py`: unexpected errors bypass the structured error response.
8. `app/tavily.py`: a Tavily error payload looks like an empty result.
9. `app/mcp_client.py`: `MCP_FAILURES` can hide programming errors.
10. `tests/test_e2e.py`: the startup loop has no limit, and no test proves that the MCP timeout fires.
