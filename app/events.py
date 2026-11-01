"""Step events for the graph sidebar. Only allow-listed fields leave the server."""

import asyncio
from datetime import date
from typing import Any

from loguru import logger

QUEUE_SIZE = 200
SAFE_FIELDS = (
    "destination",
    "check_in",
    "check_out",
    "adults",
    "budget_total_inr",
    "interests",
    "missing_fields",
    "field_error",
    "answered",
    "budget_totals",
    "budget_source",
    "stay_source",
    "places_available",
)
COUNTED_FIELDS = ("stay_candidates", "places")


def safe_changes(update: dict[str, Any] | None) -> dict[str, Any]:
    """Keep fields that are safe to show. The customer message is never one of them."""
    update = update or {}
    changes: dict[str, Any] = {}
    for name in SAFE_FIELDS:
        if name in update:
            value = update[name]
            changes[name] = value.isoformat() if isinstance(value, date) else value
    for name in COUNTED_FIELDS:
        if name in update:
            changes[f"{name}_count"] = len(update[name])
    return changes


class EventHub:
    """Send each event to every open page. The agent never waits for a page."""

    def __init__(self) -> None:
        self._queues: set[asyncio.Queue[dict[str, Any]]] = set()

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(QUEUE_SIZE)
        self._queues.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._queues.discard(queue)

    def publish(self, event: dict[str, Any]) -> None:
        logger.debug(f"EVENT | {event}")
        for queue in self._queues:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(event)


hub = EventHub()
