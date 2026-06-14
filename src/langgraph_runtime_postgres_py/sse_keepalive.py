"""SSE interrupt keep-alive patch for Postgres runtime.

Applies a monkey-patch to langgraph_api.sse.EventSourceResponse so that
interrupt events do not close the SSE connection but instead keep it alive
while waiting for human-in-the-loop resolution.
"""

from __future__ import annotations

import asyncio
import json

import structlog

logger = structlog.stdlib.get_logger(__name__)

INTERRUPT_EVENT = "interrupt"
RESUME_EVENT = "resume"
INTERRUPT_TIMEOUT_SECONDS = 3600  # 1 hour max wait


async def _wait_for_resume(thread_id: str, run_id: str, timeout: int = INTERRUPT_TIMEOUT_SECONDS) -> dict | None:
    """Wait for a run to resume from interrupt via polling."""
    from langgraph_runtime_postgres_py.database import _get_pool
    deadline = asyncio.get_event_loop().time() + timeout

    while asyncio.get_event_loop().time() < deadline:
        try:
            pool = await _get_pool()
            async with pool.connection() as conn:
                rows = await conn.execute(
                    "SELECT status FROM runs WHERE run_id = %s", (run_id,)
                )
                if rows and rows[0]["status"] not in ("interrupted", "pending"):
                    return {"status": rows[0]["status"]}
                # Also check for new checkpoints
                from langgraph_runtime_postgres_py.checkpoint import Checkpointer
                checkpointer = Checkpointer()
                tup = await checkpointer.aget_tuple(
                    {"configurable": {"thread_id": thread_id}}
                )
                if tup and tup.metadata.get("source") != "interrupt":
                    return {"checkpoint_id": tup.checkpoint["id"]}
        except Exception:
            logger.warning("resume poll failed", exc_info=True)
        await asyncio.sleep(2)
    return None


def json_to_sse(event_type: str, data: dict) -> bytes:
    payload = json.dumps(data, default=str)
    return f"event: {event_type}\ndata: {payload}\n\n".encode()


def apply_sse_patch() -> None:
    """Apply the SSE keep-alive patch for Postgres runtime."""
    from langgraph_api import sse as sse_module

    original_stream_response = sse_module.EventSourceResponse.stream_response

    async def patched_stream_response(self, send):
        """Patched stream_response that keeps connection alive on interrupt."""
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [
                [b"content-type", b"text/event-stream"],
                [b"cache-control", b"no-cache"],
                [b"connection", b"keep-alive"],
            ],
        })

        async with self._async_body_iterator() as body:
            try:
                async for data in body:
                    # Check for interrupt signal
                    if isinstance(data, tuple) and len(data) == 2 and data[0] == INTERRUPT_EVENT:
                        interrupt_info = data[1]
                        await send({
                            "type": "http.response.body",
                            "body": json_to_sse(INTERRUPT_EVENT, interrupt_info),
                            "more_body": True,
                        })
                        # Wait for resume
                        resume_data = await _wait_for_resume(
                            interrupt_info.get("thread_id", ""),
                            interrupt_info.get("run_id", ""),
                        )
                        if resume_data:
                            await send({
                                "type": "http.response.body",
                                "body": json_to_sse(RESUME_EVENT, resume_data),
                                "more_body": True,
                            })
                        continue

                    # Normal event
                    if isinstance(data, (str, bytes)):
                        body_bytes = data if isinstance(data, bytes) else data.encode()
                    else:
                        body_bytes = json.dumps(data, default=str).encode()
                    await send({
                        "type": "http.response.body",
                        "body": body_bytes,
                        "more_body": True,
                    })
            except Exception:
                logger.exception("sse stream error")

        await send({"type": "http.response.body", "body": b"", "more_body": False})

    sse_module.EventSourceResponse.stream_response = patched_stream_response
    logger.info("SSE keep-alive patch applied")