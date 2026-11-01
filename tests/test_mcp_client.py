import json

import pytest
from loguru import logger

from app import mcp_client
from app.config import MCP_CONFIG_PATH, ROOT


def test_config_file_holds_no_secret_value() -> None:
    server = json.loads(MCP_CONFIG_PATH.read_text(encoding="utf-8"))["mcpServers"][
        "tavily"
    ]
    assert server["headers"]["Authorization"] == "Bearer ${tavilyApiKey}"
    assert "?" not in server["url"]


def test_expand_replaces_names_in_nested_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("tavilyApiKey", "abc")
    result = mcp_client.expand(
        {"a": ["${PROJECT_ROOT}/x"], "b": {"c": "Bearer ${tavilyApiKey}"}, "d": 1}
    )
    assert result == {
        "a": [f"{ROOT.as_posix()}/x"],
        "b": {"c": "Bearer abc"},
        "d": 1,
    }


def test_missing_variable_names_the_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("tavilyApiKey", raising=False)
    with pytest.raises(mcp_client.MissingSecretError, match="tavilyApiKey"):
        mcp_client.load_server("tavily")


def test_load_server_runs_published_airbnb_server_with_npx() -> None:
    server = mcp_client.load_server("airbnb")
    assert server["command"] == "npx"
    assert server["args"] == ["-y", "@openbnb/mcp-server-airbnb", "--ignore-robots-txt"]
    assert "env" not in server


def test_open_client_does_not_log_the_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("tavilyApiKey", "very-secret-value")
    messages: list[str] = []
    sink = logger.add(messages.append, level="DEBUG")
    try:
        mcp_client.open_client("tavily")
    finally:
        logger.remove(sink)
    assert messages
    assert not any("very-secret-value" in message for message in messages)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://x.test/a", True),
        ("https://", False),
        ("http://x.test", False),
        ("javascript:alert(1)", False),
        (None, False),
    ],
)
def test_is_https_url(url: object, expected: bool) -> None:
    assert mcp_client.is_https_url(url) is expected
