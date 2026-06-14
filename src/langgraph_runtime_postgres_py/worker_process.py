"""Standalone worker process entry point.

Usage:
    python -m langgraph_runtime_postgres_py.worker_process
"""

import asyncio
import os
import signal
import sys


async def main() -> None:
    """Start a worker process consuming from Redis Streams."""
    os.environ.setdefault("LANGGRAPH_RUNTIME_EDITION", "postgres")

    from langgraph_runtime_postgres_py.database import start_pool, stop_pool
    from langgraph_runtime_postgres_py.checkpoint import start_checkpointer, exit_checkpointer
    from langgraph_runtime_postgres_py.run_queue import start_redis, stop_redis, queue
    from langgraph_runtime_postgres_py.store import collect_store_from_env, get_store, exit_store

    shutdown = asyncio.Event()

    def _handle_signal(signum, frame):
        shutdown.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    await start_pool()
    await start_checkpointer()
    await start_redis()
    await collect_store_from_env()
    await get_store()

    queue_task = asyncio.create_task(queue())

    await shutdown.wait()

    queue_task.cancel()
    try:
        await queue_task
    except asyncio.CancelledError:
        pass

    await exit_store()
    await exit_checkpointer()
    await stop_redis()
    await stop_pool()


if __name__ == "__main__":
    asyncio.run(main())
