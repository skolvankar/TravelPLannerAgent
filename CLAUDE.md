# CLAUDE.md

Minimal teaching slice of the Travel Planner PRD. It shows a FastMCP server, two external MCP servers (Airbnb and Tavily), a three-node LangGraph agent, a form that the server describes with Prefab, and a live view of each graph step.

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
        └─► LangGraph intake, estimate_budget, and process (app/graph.py)
              ├─► Airbnb MCP over stdio (vendored server)
              └─► Tavily MCP over HTTP (remote server)
```

- `intake` calls the LLM once. It then loops to itself and pauses with `interrupt()` until no required field is missing. Each pause asks for one field, the first missing one in `REQUIRED_FIELDS` order. Budget is last, because its options need the other fields.
- `estimate_budget` runs once for each set of trip details, just before the budget question. It searches Airbnb for the destination, dates, and adults with no price limit, and reads the whole-stay rupee price from each listing label. The four tiers are the 25th, 50th, 75th, and 100th percentile prices (`BUDGET_PERCENTILES`), rounded up. With fewer than `MIN_PRICED_STAYS` prices, it asks the LLM for the nightly price for one adult in each tier, and each option is that price x adults x nights. If that call fails too, it uses `DEFAULT_NIGHTLY_RATES_INR`. The form says which source it used. It is a separate node, because a resume runs `intake` again from the top, so a call inside `intake` would repeat.
- `process` uses no LLM. It calls Airbnb and Tavily in parallel.
- `mcp_client.json` holds all MCP servers. It uses `${NAME}` for secrets, never values. `app/mcp_client.py` expands the names and opens one client for each server. FastMCP does not expand `${NAME}` itself.
- `app/ui.py` builds Prefab components. The tools return them as JSON in `structuredContent`.
- `app/static/app.js` draws that JSON as native HTML. It supports only the components in `drawers`. A new component in `ui.py` needs a new drawer in `app.js`. A test checks this.
- `app/graph.py` runs the graph with `stream_mode=["tasks", "custom"]` and publishes events through `app/events.py`. Task events include the node input, which holds the customer message. Never publish `chunk["input"]`. `safe_changes` is the allow list.

## Decisions that differ from the defaults

| Topic | Decision | Why |
|---|---|---|
| Model | `claude-haiku-5-5` with adaptive thinking. `medium` effort for extraction, `low` for the budget estimate | The user chose this model. It rejects `budget_tokens`, so effort sets the depth and `max_tokens` is the hard limit. The global file says `claude-haiku-4-5`. This file wins on model choice |
| API-first rule | No FastAPI. MCP tools and three small routes are the only interface | User-approved exception. The goal is to show MCP |
| Tavily transport | Remote HTTP with an `Authorization` header | The user chose the remote server. The PRD says `npx`. The header keeps the key out of URLs |
| Key name | `tavilyApiKey` in `.env` | The user chose this name |
| Tavily tools | `tavily_search` only | The PRD puts `tavily_extract` behind a human pause, which is out of scope |
| PRD robots rule | `--ignore-robots-txt` is on | The user approved this. The PRD says the flag stays off |
| PRD domain allow list | Not included | Minimal scope. Each result shows its source link |
| PRD scope | Three nodes only. No Laya, supervisor, Trip Rules, or planner | User-approved minimal scope |
| Form | One question at a time | The user asked for this |
| Budget options | Percentiles of live Airbnb stay prices for the trip. LLM estimate, then fixed rates, as fallbacks | The user asked for live Airbnb prices. The sample listings are for Goa, so they cannot price another trip |
| Sample data location | `app/fixtures/`, not `data/` or `tests/` | `data/` is protected, and the application reads this file at runtime |
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
6. Live budget tiers come from one page of Airbnb results (about 18 stays), and the price comes from label text such as "₹10,000 for 4 nights". A label change sends the trip to the LLM estimate, which is a guess, checked only for order and limits. A trip with a missing budget makes two Airbnb searches.
7. Tavily results come from any website. The text is shown as plain text, and no LLM reads it. Adding an LLM step needs a prompt injection review.

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
