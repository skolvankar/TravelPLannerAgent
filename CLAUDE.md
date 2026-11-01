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
              ├─► Airbnb MCP over stdio (published server through npx)
              └─► Tavily MCP over HTTP (remote server)
```

- `intake` calls the LLM once to extract the trip. It then loops to itself and pauses with `interrupt()` for one missing field at a time, in the `REQUIRED_FIELDS` order, until no required field is missing. Only the asked field is read from the answers. The budget is always last.
- When the budget is the next question, `intake` calls the LLM a second time, once for each destination, through `app/budget.py` `estimate_rates`. The rates are stored in the state, so a resume does not call the LLM again. The choices are `rate x rooms x nights`, with `ADULTS_PER_ROOM` adults in each room, rounded to `BUDGET_ROUNDING_INR`. A failed or unusable estimate uses `DEFAULT_NIGHTLY_RATES`. No LLM call happens before `interrupt()`, because a resume runs the node again from the top.
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
| Missing fields | One question at a time, budget last | The user chose this on 2026-11-01 |
| Budget choices | Four levels from an LLM estimate of nightly rates for the destination, times rooms and nights | The user chose an LLM estimate over a fixed city table on 2026-11-01. It works for any destination. The rates are a guess, not live prices |
| Airbnb fallback | Sample listings only for a Goa trip. Other places get a message and an Airbnb search link | The user chose this on 2026-11-01. Goa listings for another place would mislead |
| Airbnb server | Published `@openbnb/mcp-server-airbnb` through `npx -y`, with no patch and no `env` | The user chose this signature on 2026-11-01. It replaces the vendored 0.3.0 copy with the `AIRBNB_BASE_URL` patch. The published 0.3.0 hardcodes `airbnb.com`, so see open issue 7 |
| PRD robots rule | `--ignore-robots-txt` is on | The user approved this. The PRD says the flag stays off |
| PRD domain allow list | Not included | Minimal scope. Each result shows its source link |
| PRD scope | Two nodes only. No Laya, supervisor, Trip Rules, or planner | User-approved minimal scope |
| Sample data location | `app/fixtures/`, not `data/` or `tests/` | `data/` is protected, and the application reads this file at runtime |
| Playwright | The `playwright` package directly, not the `pytest-playwright` plugin | The plugin keeps an event loop open, which breaks the async tests that run after it |

## Vendored code

- `app/static/vendor/mermaid.min.js` is Mermaid 11.17.2, so the demo needs no CDN.

## Known open issues

1. The Airbnb server parses HTML, so a site change can break it. For a trip to `SAMPLE_DESTINATION` (Goa) the page then shows recorded listings with a "SAMPLE DATA" label. For any other place it shows "Live Airbnb stays are not available right now." Both cases show a link to an Airbnb search for the destination, dates, and adults on `AIRBNB_SEARCH_BASE_URL`.
2. Paused trips are in memory. A server restart loses them, and the page asks the user to send the request again. Paused trips expire after one hour.
3. The tools and routes have no authentication. The server binds to `127.0.0.1` and rejects other Host names.
4. The sample listings are from Goa on 2026-11-01. They are not results for the search of the user, and the page says so.
5. Every open tab receives the events of every trip. This is acceptable for a local single-user demo, but not for a shared server.
6. Tavily results come from any website. The text is shown as plain text, and no LLM reads it. Adding an LLM step needs a prompt injection review.
7. The published Airbnb server hardcodes `https://www.airbnb.com` (line 137 of `dist/index.js`, upstream issue #60). From Indian IP addresses that page is an 852-byte stub, while `airbnb.co.in` returns the real results. On such a network every live search falls back to the sample listings. The first `npx` run also downloads the package, which counts toward the 60-second MCP timeout.

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
