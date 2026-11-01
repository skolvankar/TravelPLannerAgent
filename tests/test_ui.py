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
OPTIONS = [
    {"value": "7000", "label": "Economy: ₹7,000"},
    {"value": "15000", "label": "Mid-range: ₹15,000"},
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


def button_of(app: PrefabApp) -> dict[str, Any]:
    return next(n for n in nodes(app) if n["type"] == "Button")


def test_form_asks_only_the_first_missing_field() -> None:
    all_nodes = nodes(build_form("t", ["check_in", "adults", "budget_total_inr"], None))
    named = {n["name"]: n["type"] for n in all_nodes if n.get("name")}
    assert named == {"check_in": "DatePicker"}


def test_budget_radios_come_from_the_options() -> None:
    app = build_form("t", ["budget_total_inr"], None, OPTIONS)
    radios = [(n["option"], n["label"]) for n in nodes(app) if n["type"] == "Radio"]
    assert radios == [
        ("7000", "Economy: ₹7,000"),
        ("15000", "Mid-range: ₹15,000"),
    ]


def test_estimated_budget_shows_a_note_and_live_budget_does_not() -> None:
    estimated = build_form("t", ["budget_total_inr"], None, OPTIONS, False)
    live = build_form("t", ["budget_total_inr"], None, OPTIONS, True)
    assert "general estimates" in json.dumps(estimated.to_json())
    assert "general estimates" not in json.dumps(live.to_json())


def test_button_says_next_until_the_last_question() -> None:
    assert button_of(build_form("t", ["check_in", "adults"], None))["label"] == "Next"
    assert button_of(build_form("t", ["adults"], None))["label"] == "Search stays"


def test_destination_uses_a_text_input() -> None:
    all_nodes = nodes(build_form("t", ["destination"], None))
    assert any(n["type"] == "Input" and n["name"] == "destination" for n in all_nodes)


def test_adults_uses_a_number_input() -> None:
    field = next(
        n for n in nodes(build_form("t", ["adults"], None)) if n.get("name") == "adults"
    )
    assert field["inputType"] == "number"


def test_button_calls_submit_tool_with_state_templates() -> None:
    button = button_of(build_form("abc", ["adults", "budget_total_inr"], None))
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
    forms = [build_form("t", fields[i:], "e", OPTIONS) for i in range(len(fields))]
    for app in (*forms, results(), build_error("C", "d")):
        assert {n["type"] for n in nodes(app)} <= drawn


def test_error_view_has_structured_state() -> None:
    state = build_error("VALIDATION_ERROR", "Bad").to_json()["state"]
    assert state == {"status": "error", "code": "VALIDATION_ERROR", "detail": "Bad"}
