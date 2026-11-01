import json
import re
from typing import Any

import pytest
from prefab_ui import PrefabApp

from app.airbnb import SOURCE_LIVE, SOURCE_SAMPLE
from app.config import STATIC_DIR
from app.ui import build_error, build_form, build_results, format_inr

LISTING = {
    "name": "Sea Flat",
    "url": "https://x.test/1",
    "price": "₹1",
    "rating": "5",
    "details": "1 bed",
}
PLACE = {"title": "Beach", "url": "https://x.test/p", "summary": "Sand"}
OPTIONS = [
    {"tier": "Budget", "total_inr": 6000, "per_night_inr": 2000},
    {"tier": "Mid-range", "total_inr": 120000, "per_night_inr": 40000},
]


def results(source: str = SOURCE_LIVE, destination: str = "Goa") -> PrefabApp:
    return build_results(destination, [LISTING], source, [PLACE], True)


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


def budget_form(source: str = "live") -> PrefabApp:
    return build_form(
        "t",
        "budget_total_inr",
        None,
        answered=3,
        budget_options=OPTIONS,
        budget_source=source,
    )


def test_form_has_one_control_for_the_asked_field() -> None:
    named = [n for n in nodes(build_form("t", "check_in", None)) if n.get("name")]
    assert [(n["name"], n["type"]) for n in named] == [("check_in", "DatePicker")]


def test_form_shows_progress_and_next_until_the_last_question() -> None:
    app = build_form("t", "check_out", None, answered=1, remaining=3)
    text = json.dumps(app.to_json())
    assert "Question 2 of 4" in text
    button = next(n for n in nodes(app) if n["type"] == "Button")
    assert button["label"] == "Next"
    last = next(n for n in nodes(budget_form()) if n["type"] == "Button")
    assert last["label"] == "Search stays"


def test_budget_offers_the_computed_options() -> None:
    all_nodes = nodes(budget_form())
    radios = [(n["option"], n["label"]) for n in all_nodes if n["type"] == "Radio"]
    assert radios == [
        ("6000", "Budget: ₹6,000 (about ₹2,000 a night)"),
        ("120000", "Mid-range: ₹1,20,000 (about ₹40,000 a night)"),
    ]
    assert "live Airbnb prices" in json.dumps(budget_form().to_json())


@pytest.mark.parametrize(
    ("source", "note"),
    [("estimate", "Claude estimated"), ("default", "general prices")],
)
def test_budget_says_when_prices_are_not_live(source: str, note: str) -> None:
    text = json.dumps(budget_form(source).to_json())
    assert "Live Airbnb prices" in text
    assert "not available" in text
    assert note in text


def test_destination_uses_text_and_adults_uses_a_number_input() -> None:
    destination = next(
        n for n in nodes(build_form("t", "destination", None)) if n.get("name")
    )
    assert destination["type"] == "Input"
    adults = next(n for n in nodes(build_form("t", "adults", None)) if n.get("name"))
    assert adults["inputType"] == "number"


def test_button_calls_submit_tool_with_state_templates() -> None:
    button = next(
        n for n in nodes(build_form("abc", "adults", None)) if n["type"] == "Button"
    )
    assert button["onClick"]["action"] == "toolCall"
    assert button["onClick"]["tool"] == "submit_trip_details"
    assert button["onClick"]["arguments"] == {
        "thread_id": "abc",
        "adults": "{{ adults }}",
    }


def test_form_shows_error() -> None:
    assert "Bad date" in json.dumps(build_form("t", "adults", "Bad date").to_json())


def test_format_inr_uses_indian_digit_groups() -> None:
    assert format_inr(500) == "₹500"
    assert format_inr(25000) == "₹25,000"
    assert format_inr(100000) == "₹1,00,000"
    assert format_inr(12345678) == "₹1,23,45,678"


def test_live_results_show_stays_and_places() -> None:
    text = json.dumps(results().to_json())
    assert "Stays in Goa" in text
    assert "Things to do in Goa" in text
    assert "SAMPLE DATA" not in text


def test_sample_results_have_clear_label() -> None:
    text = json.dumps(results(SOURCE_SAMPLE, "Pune").to_json())
    assert "SAMPLE DATA" in text
    assert "Stays in Pune" not in text


def test_unavailable_places_show_a_message() -> None:
    app = build_results("Goa", [LISTING], SOURCE_LIVE, [], False)
    assert "Places are not available" in json.dumps(app.to_json())


def test_views_use_only_components_that_the_page_draws() -> None:
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    block = re.search(r"const drawers = \{(.*?)\n\};", script, re.DOTALL)
    assert block is not None
    drawn = set(re.findall(r"^  (\w+):", block.group(1), re.MULTILINE))
    # drawRadioGroup draws Radio children.
    drawn.add("Radio")
    fields = ["destination", "check_in", "check_out", "adults"]
    forms = [build_form("t", field, "e") for field in fields]
    views = (*forms, budget_form(), results(), build_error("C", "d"))
    for app in views:
        assert {n["type"] for n in nodes(app)} <= drawn


def test_error_view_has_structured_state() -> None:
    state = build_error("VALIDATION_ERROR", "Bad").to_json()["state"]
    assert state == {"status": "error", "code": "VALIDATION_ERROR", "detail": "Bad"}
