import json
import re
from typing import Any

from prefab_ui import PrefabApp

from app.airbnb import SOURCE_LIVE, SOURCE_SAMPLE
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


BUDGET = [("15000", "Economy"), ("27000", "Standard")]


def test_form_has_one_control_for_the_asked_field() -> None:
    named = [n for n in nodes(build_form("t", "check_in", None, 3)) if n.get("name")]
    assert [(n["name"], n["type"]) for n in named] == [("check_in", "DatePicker")]


def test_budget_radios_come_from_the_given_options() -> None:
    all_nodes = nodes(build_form("t", "budget_total_inr", None, 0, BUDGET))
    radios = [n["option"] for n in all_nodes if n["type"] == "Radio"]
    assert radios == ["15000", "27000"]


def test_destination_uses_text_and_adults_uses_a_number_input() -> None:
    destination = next(
        n for n in nodes(build_form("t", "destination", None)) if n.get("name")
    )
    assert destination["type"] == "Input"
    adults = next(n for n in nodes(build_form("t", "adults", None)) if n.get("name"))
    assert adults["inputType"] == "number"


def test_form_counts_the_questions_left() -> None:
    text = json.dumps(build_form("t", "check_in", None, 2).to_json())
    assert "2 more questions after this." in text
    assert "Next" in text
    last = json.dumps(build_form("t", "budget_total_inr", None, 0, BUDGET).to_json())
    assert "more question" not in last
    assert "Search stays" in last


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
    forms = tuple(build_form("t", name, "e", 1, BUDGET) for name in fields)
    views = (*forms, results(), build_error("C", "d"))
    for app in views:
        assert {n["type"] for n in nodes(app)} <= drawn


def test_error_view_has_structured_state() -> None:
    state = build_error("VALIDATION_ERROR", "Bad").to_json()["state"]
    assert state == {"status": "error", "code": "VALIDATION_ERROR", "detail": "Bad"}
