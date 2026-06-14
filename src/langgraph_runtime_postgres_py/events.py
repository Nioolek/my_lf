"""Redis Pub/Sub event bus for process event notifications."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import structlog

logger = structlog.stdlib.get_logger(__name__)

EVENTS_CHANNEL = "lg:events"


class EventType(str, Enum):
    RUN_CREATED = "run.created"
    RUN_STARTED = "run.started"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_INTERRUPTED = "run.interrupted"
    RUN_RESUMED = "run.resumed"
    RUN_TIMEOUT = "run.timeout"
    NODE_STARTED = "node.started"
    NODE_COMPLETED = "node.completed"
    THREAD_UPDATED = "thread.updated"


async def _get_redis():
    from langgraph_runtime_postgres_py.run_queue import get_redis
    return await get_redis()


async def publish_event(event_type: EventType, payload: dict[str, Any]) -> None:
    """Publish an event to Redis Pub/Sub."""
    try:
        redis = await _get_redis()
        await redis.publish(EVENTS_CHANNEL, json.dumps({
            "type": event_type.value,
            "payload": payload,
            "timestamp": datetime.now(UTC).isoformat(),
        }))
    except Exception:
        logger.warning("failed to publish event", event_type=event_type.value, exc_info=True)


async def subscribe_events(
    event_types: list[EventType] | None = None,
    thread_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Subscribe to events, optionally filtering by type and thread_id."""
    redis = await _get_redis()
    async with redis.pubsub() as pubsub:
        await pubsub.subscribe(EVENTS_CHANNEL)
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                event = json.loads(message["data"])
            except json.JSONDecodeError:
                continue
            if event_types and event["type"] not in [t.value for t in event_types]:
                continue
            if thread_id and event["payload"].get("thread_id") != thread_id:
                continue
            yield event
