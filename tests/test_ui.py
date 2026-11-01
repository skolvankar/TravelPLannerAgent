import json
import re
from typing import Any

from prefab_ui import PrefabApp

from app.airbnb import SOURCE_LIVE, SOURCE_SAMPLE
from app.budget import BASIS_ESTIMATE, BASIS_LIVE
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


BUDGET_CHOICES = [
    {"value": "9000", "label": "Budget: ₹9,000"},
    {"value": "12000", "label": "Comfortable: ₹12,000"},
    {"value": "18000", "label": "Premium: ₹18,000"},
]


def test_form_asks_only_the_first_missing_field() -> None:
    types = {
        n.get("name"): n["type"]
        for n in nodes(
            build_form("t", ["check_in", "adults", "budget_total_inr"], None)
        )
    }
    assert types["check_in"] == "DatePicker"
    assert "adults" not in types
    assert "budget_total_inr" not in types


def test_budget_uses_the_priced_choices_as_radio_buttons() -> None:
    form = build_form("t", ["budget_total_inr"], None, 1, BUDGET_CHOICES, BASIS_LIVE)
    all_nodes = nodes(form)
    radios = [n["option"] for n in all_nodes if n["type"] == "Radio"]
    assert radios == ["9000", "12000", "18000"]
    assert "live Airbnb prices" in json.dumps(form.to_json())


def test_estimated_budget_choices_are_labelled() -> None:
    form = build_form(
        "t", ["budget_total_inr"], None, 1, BUDGET_CHOICES, BASIS_ESTIMATE
    )
    assert "ESTIMATE" in json.dumps(form.to_json())


def test_destination_uses_text() -> None:
    all_nodes = nodes(build_form("t", ["destination"], None))
    assert any(n["type"] == "Input" and n["name"] == "destination" for n in all_nodes)


def test_button_says_next_until_the_last_question() -> None:
    def label(remaining: int) -> str:
        form = build_form("t", ["adults"], None, remaining)
        return next(n for n in nodes(form) if n["type"] == "Button")["label"]

    assert label(3) == "Next"
    assert label(1) == "Search stays"


def test_adults_uses_a_number_input() -> None:
    field = next(
        n for n in nodes(build_form("t", ["adults"], None)) if n.get("name") == "adults"
    )
    assert field["inputType"] == "number"


def test_button_calls_submit_tool_with_state_templates() -> None:
    button = next(
        n for n in nodes(build_form("abc", ["adults"], None)) if n["type"] == "Button"
    )
    assert button["onClick"]["action"] == "toolCall"
    assert button["onClick"]["tool"] == "submit_trip_details"
    assert button["onClick"]["arguments"] == {
        "thread_id": "abc",
        "adults": "{{ adults }}",
    }


def test_form_shows_error() -> None:
    assert "Bad date" in json.dumps(build_form("t", ["adults"], "Bad date").to_json())


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
    fields = ["destination", "check_in", "check_out", "adults", "budget_total_inr"]
    forms = [
        build_form("t", [name], "e", 1, BUDGET_CHOICES, BASIS_ESTIMATE)
        for name in fields
    ]
    views = (*forms, results(), build_error("C", "d"))
    for app in views:
        assert {n["type"] for n in nodes(app)} <= drawn


def test_error_view_has_structured_state() -> None:
    state = build_error("VALIDATION_ERROR", "Bad").to_json()["state"]
    assert state == {"status": "error", "code": "VALIDATION_ERROR", "detail": "Bad"}
