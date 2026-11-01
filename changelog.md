# Changelog

## Session 2: 2026-11-01

Goal: ask for one missing field at a time, and base the budget options on live Airbnb prices for the destination, the dates, and the adults.

| File | What changed | Why |
|---|---|---|
| `app/graph.py` | Each pause asks for the first missing field. New `estimate_budget` node: live price percentiles, then a Claude estimate, then default rates. One shared Claude call helper | One question at a time. Budget options that fit the trip |
| `app/airbnb.py` | New `stay_prices` and `parse_stay_price`: a search with no price limit that returns the whole-stay prices | Live prices for the budget options |
| `app/config.py` | Budget tiers, percentiles, minimum priced stays, default nightly rates, rate limit, and estimate effort | One place to change the budget settings |
| `app/ui.py` | The form draws one field, the progress, the computed budget options with Indian digit groups, and a note on the price source | One question at a time. No fixed budget amounts |
| `app/server.py` | Passes the single field and the budget options to the form | New pause data |
| `app/events.py` | Allows `answered`, `budget_totals`, and `budget_source` | Sidebar shows the estimate |
| `app/static/graph_panel.js` | The pause step names the asked field | One question at a time |
| `tests/test_graph.py`, `tests/test_airbnb.py`, `tests/test_ui.py`, `tests/test_server.py`, `tests/test_e2e.py` | Cases for the question order, repeated questions, price parsing, live tiers, both fallbacks, and estimate checks | Covers the changes |
| `CLAUDE.md` | Updated the architecture, decisions, and open issues | Context for the next session |

## Session 1, part 2: 2026-11-01

Goal: add Tavily, a single MCP config file, a live graph sidebar, and fixes for the 11 review findings.

| File | What changed | Why |
|---|---|---|
| `mcp_client.json` | New. Airbnb and Tavily settings, with `${NAME}` for secrets | One place for all MCP servers |
| `app/mcp_client.py` | New. Loader, `${NAME}` expansion, one-server client, timeout, HTTPS check | Keeps failures apart. Fixes finding 2 |
| `app/tavily.py` | New. Search text, tool call, result parser, summary cleanup | Tavily integration |
| `app/events.py` | New. Allow-listed step events for open pages | Live sidebar with no customer text |
| `app/config.py` | Removed the Airbnb dictionary, added MCP and limit settings | Settings moved to `mcp_client.json` |
| `app/airbnb.py` | Uses the loader. Parsing moved inside the `try` block | Fixes findings 2 and 3 |
| `app/graph.py` | Streams steps, adds `interests` and `places`, parallel searches, deletes finished trips, closes the Anthropic client, keeps valid answers | Sidebar and Tavily. Fixes findings 5, 8, and 9 |
| `app/server.py` | Adds `/events` and `/graph`, one static route with an allow list, and the Host check | Sidebar. Fixes finding 1 |
| `app/ui.py` | Adds the places section. Adults uses a number input | Tavily. Fixes finding 4 |
| `app/static/index.html` | Sidebar layout | Live sidebar |
| `app/static/style.css` | Sidebar styles and node highlight | Live sidebar |
| `app/static/app.js` | Only the newest run draws, safe URL check, number input | Fixes findings 4, 6, and 7 |
| `app/static/graph_panel.js` | New. Diagram, highlight, step log, event stream | Live sidebar |
| `app/static/vendor/mermaid.min.js`, `mermaid.LICENSE` | New. Mermaid 11.17.2 | Draws the diagram with no CDN |
| `tests/test_graph.py`, `tests/test_airbnb.py`, `tests/test_ui.py`, `tests/test_server.py` | New cases and type hints on all functions | Covers the changes. Fixes findings 10 and 11 |
| `tests/test_mcp_client.py`, `tests/test_tavily.py`, `tests/test_events.py` | New | Covers the new modules |
| `tests/test_e2e.py` | New. Playwright test of the form and the sidebar | Fixes finding 10 |
| `pyproject.toml`, `uv.lock` | Added `playwright` as a dev dependency | Browser test |
| `.env.example` | Added `tavilyApiKey` | Key template |
| `CLAUDE.md` | Updated architecture, decisions, and open issues | Context for the next session |

## Session 1: 2026-11-01

All files are new. The goal is a minimal demo of FastMCP, the Airbnb MCP server, LangGraph, and a form that the server describes.

| File | What changed | Why |
|---|---|---|
| `app/config.py` | Model settings, Airbnb server dictionary, limits | One place to change the model or the server |
| `app/graph.py` | State, `intake`, `process`, start and resume functions | The two-node agent. A blank submit now shows a message |
| `app/airbnb.py` | FastMCP client, listing parser, sample fallback | Airbnb integration. The demo continues when the scraper fails |
| `app/ui.py` | Prefab form, results, and error views | The server describes the interface |
| `app/server.py` | `plan_stay`, `submit_trip_details`, page routes, logging | The FastMCP server |
| `app/static/index.html` | Query form and view area | Browser interface |
| `app/static/style.css` | Basic styles with light and dark themes | Browser interface |
| `app/static/app.js` | MCP calls and Prefab JSON drawing | Browser interface |
| `app/fixtures/airbnb_sample.json` | Five recorded Goa listings | Labelled fallback data |
| `tests/test_graph.py` | Graph, validation, and Claude request tests | Definition of Done |
| `tests/test_airbnb.py` | Parser and fallback tests | Definition of Done |
| `tests/test_ui.py` | Form and results tests | Definition of Done |
| `tests/test_server.py` | Tool and page route tests | Definition of Done |
| `vendor/mcp-server-airbnb/` | Version 0.3.0 with the `AIRBNB_BASE_URL` patch | The published server cannot read listings from this network |
| `pyproject.toml`, `uv.lock` | Project and pinned dependencies | Created with `uv` |
| `pytest.ini` | Test settings | Keeps `pyproject.toml` free of manual edits |
| `.gitignore`, `.env.example` | Ignored paths and key template | Protects `.env` |
| `CLAUDE.md` | Run steps, decisions, open issues | Context for the next session |
| `changelog.md` | This file | Project rule |
