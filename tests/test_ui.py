import json
import re
from typing import Any

from prefab_ui import PrefabApp

from app.airbnb import SOURCE_LIVE, SOURCE_SAMPLE, SOURCE_UNAVAILABLE
from app.config import STATIC_DIR
from app.ui import build_error, build_form, build_results

LISTING = {
    "name": "Sea Flat",
    "url": "https://x.test/1",
    "price": "₹1",
    "rating": "5",
    "details": "1 bed",
}
PLACE = {"title": "Beach", "url": "https://x.test/p", "summary": "Sand"}
SEARCH_URL = "https://x.test/search"


def results(source: str = SOURCE_LIVE, destination: str = "Goa") -> PrefabApp:
    listings = [] if source == SOURCE_UNAVAILABLE else [LISTING]
    return build_results(destination, listings, source, [PLACE], True, SEARCH_URL)


def links(app: PrefabApp) -> list[str]:
    return [n["href"] for n in nodes(app) if n["type"] == "Link"]


def nodes(app: PrefabApp) -> list[dict[str, Any]]:
    """Return every component in the view, depth first."""
    tree = app.to_json()
    found: list[dict[str, Any]] = []

    def walk(node: dict[str, Any]) -> None:
        found.append(node)
        for child in node.get("children", []):
            walk(child)

    walk(tree["view"])
    return found


FIELDS = ["destination", "check_in", "check_out", "adults", "budget_total_inr"]
BUDGET_OPTIONS = [
    {"value": "9000", "label": "Budget · ₹9,000"},
    {"value": "18000", "label": "Mid-range · ₹18,000"},
]


def controls(app: PrefabApp) -> dict[str, str]:
    # Prefab gives each Radio its own name, so only the controls count.
    return {
        n["name"]: n["type"]
        for n in nodes(app)
        if n.get("name") and n["type"] != "Radio"
    }


def button(app: PrefabApp) -> dict[str, Any]:
    return next(n for n in nodes(app) if n["type"] == "Button")


def test_form_has_one_control_for_the_asked_field() -> None:
    assert controls(build_form("t", "check_in", 3, None)) == {"check_in": "DatePicker"}
    assert controls(build_form("t", "destination", 4, None)) == {"destination": "Input"}


def test_budget_uses_the_given_choices() -> None:
    app = build_form("t", "budget_total_inr", 0, None, BUDGET_OPTIONS)
    radios = [(n["option"], n["label"]) for n in nodes(app) if n["type"] == "Radio"]
    assert radios == [("9000", "Budget · ₹9,000"), ("18000", "Mid-range · ₹18,000")]
    assert controls(app) == {"budget_total_inr": "RadioGroup"}


def test_adults_uses_a_number_input() -> None:
    field = next(
        n
        for n in nodes(build_form("t", "adults", 1, None))
        if n.get("name") == "adults"
    )
    assert field["inputType"] == "number"


def test_button_calls_submit_tool_with_only_the_asked_field() -> None:
    action = button(build_form("abc", "adults", 1, None))["onClick"]
    assert action["action"] == "toolCall"
    assert action["tool"] == "submit_trip_details"
    assert action["arguments"] == {"thread_id": "abc", "adults": "{{ adults }}"}


def test_button_says_next_until_the_last_question() -> None:
    assert button(build_form("t", "adults", 1, None))["label"] == "Next"
    last = build_form("t", "budget_total_inr", 0, None, BUDGET_OPTIONS)
    assert button(last)["label"] == "Search stays"


def test_form_counts_the_questions_left() -> None:
    assert "3 more questions" in json.dumps(
        build_form("t", "check_in", 3, None).to_json()
    )
    assert "1 more question after" in json.dumps(
        build_form("t", "adults", 1, None).to_json()
    )
    assert "more question" not in json.dumps(
        build_form("t", "budget_total_inr", 0, None, BUDGET_OPTIONS).to_json()
    )


def test_form_shows_error() -> None:
    assert "Bad date" in json.dumps(build_form("t", "adults", 1, "Bad date").to_json())


def test_live_results_show_stays_and_places() -> None:
    text = json.dumps(results().to_json())
    assert "Stays in Goa" in text
    assert "Things to do in Goa" in text
    assert "SAMPLE DATA" not in text
    assert SEARCH_URL not in links(results())


def test_sample_results_have_clear_label_and_search_link() -> None:
    app = results(SOURCE_SAMPLE, "Goa")
    text = json.dumps(app.to_json())
    assert "SAMPLE DATA" in text
    assert "Stays in Goa" not in text
    assert SEARCH_URL in links(app)


def test_unavailable_stays_show_a_message_and_search_link() -> None:
    app = results(SOURCE_UNAVAILABLE, "Jaipur")
    text = json.dumps(app.to_json())
    assert "Stays in Jaipur" in text
    assert "Live Airbnb stays are not available right now." in text
    assert "Search Airbnb for stays in Jaipur" in text
    assert "SAMPLE DATA" not in text
    assert "Airbnb returned no stays" not in text
    assert SEARCH_URL in links(app)


def test_unavailable_places_show_a_message() -> None:
    app = build_results("Goa", [LISTING], SOURCE_LIVE, [], False, SEARCH_URL)
    assert "Places are not available" in json.dumps(app.to_json())


def test_views_use_only_components_that_the_page_draws() -> None:
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    block = re.search(r"const drawers = \{(.*?)\n\};", script, re.DOTALL)
    assert block is not None
    drawn = set(re.findall(r"^  (\w+):", block.group(1), re.MULTILINE))
    # drawRadioGroup draws Radio children.
    drawn.add("Radio")
    forms = [build_form("t", field, 1, "e", BUDGET_OPTIONS) for field in FIELDS]
    for app in (*forms, results(), build_error("C", "d")):
        assert {n["type"] for n in nodes(app)} <= drawn


def test_error_view_has_structured_state() -> None:
    state = build_error("VALIDATION_ERROR", "Bad").to_json()["state"]
    assert state == {"status": "error", "code": "VALIDATION_ERROR", "detail": "Bad"}
