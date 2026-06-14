"""Redis Streams + Consumer Groups distributed task queue."""

from __future__ import annotations

import asyncio
import json
import os
import socket
from datetime import UTC, datetime
from functools import partial
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import structlog

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = structlog.stdlib.get_logger(__name__)

RUNS_STREAM = "lg:runs"
CONSUMER_GROUP = "workers"
WORKER_HEARTBEAT_SECS = 10
STALE_WORKER_TIMEOUT_SECS = 60
STALE_RUN_TIMEOUT_SECS = 300

_redis: "Redis | None" = None


async def get_redis() -> "Redis":
    global _redis
    if _redis is None:
        import redis.asyncio as aioredis
        from langgraph_api import config as api_config
        uri = api_config.REDIS_URI
        if not uri:
            raise RuntimeError(
                "REDIS_URI is required for langgraph_runtime_postgres_py queue. "
                "Set REDIS_URI=redis://localhost:6379"
            )
        _redis = aioredis.from_url(
            uri,
            max_connections=api_config.REDIS_MAX_CONNECTIONS,
            socket_connect_timeout=api_config.REDIS_CONNECT_TIMEOUT,
        )
    return _redis


async def start_redis() -> None:
    redis = await get_redis()
    await redis.ping()
    try:
        await redis.xgroup_create(RUNS_STREAM, CONSUMER_GROUP, id="0", mkstream=True)
    except Exception:
        pass  # Group already exists
    logger.info("redis connected")


async def stop_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.close()
        _redis = None
        logger.info("redis disconnected")


def _worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}-{uuid4().hex[:8]}"


async def enqueue_run(run: dict) -> str:
    """Add a run to the Redis Stream for worker consumption."""
    redis = await get_redis()
    msg_id = await redis.xadd(RUNS_STREAM, {
        "run_id": str(run["run_id"]),
        "thread_id": str(run.get("thread_id", "")),
        "assistant_id": str(run.get("assistant_id", "")),
        "attempt": str(run.get("attempt", 1)),
        "enqueued_at": datetime.now(UTC).isoformat(),
    })
    logger.debug("enqueued run", run_id=str(run["run_id"]), msg_id=msg_id)
    return msg_id


async def queue() -> None:
    """Main consumption loop — Redis Streams consumer group."""
    worker_id = _worker_id()
    redis = await get_redis()
    consumer_name = f"{worker_id}"

    from langgraph_api import config as api_config
    from langgraph_api.worker import worker as run_worker
    from langgraph_runtime_postgres_py.events import EventType, publish_event

    concurrency = api_config.N_JOBS_PER_WORKER
    sem = asyncio.Semaphore(concurrency)
    active_tasks: set[asyncio.Task] = set()

    async def on_run_done(task: asyncio.Task, msg_id: bytes) -> None:
        active_tasks.discard(task)
        try:
            result = task.result()
            await redis.xack(RUNS_STREAM, CONSUMER_GROUP, msg_id)
            await redis.xdel(RUNS_STREAM, msg_id)
            if result:
                await publish_event(EventType.RUN_COMPLETED, {
                    "run_id": str(result.get("run", {}).get("run_id", "")),
                    "status": result.get("status", "success"),
                })
        except Exception:
            logger.exception("run failed", worker_id=worker_id)

    async def heartbeat_loop() -> None:
        while True:
            try:
                from langgraph_runtime_postgres_py.database import _get_pool
                pool = await _get_pool()
                async with pool.connection() as conn:
                    await conn.execute(
                        """INSERT INTO worker_registry (worker_id, hostname, pid, capacity, active_jobs, last_heartbeat, status)
                           VALUES (%s, %s, %s, %s, %s, NOW(), 'active')
                           ON CONFLICT (worker_id) DO UPDATE
                           SET last_heartbeat = NOW(), active_jobs = %s""",
                        (worker_id, socket.gethostname(), os.getpid(), concurrency, len(active_tasks), len(active_tasks)),
                    )
            except Exception:
                logger.warning("heartbeat failed", exc_info=True)
            await asyncio.sleep(WORKER_HEARTBEAT_SECS)

    async def sweep_stale_workers() -> None:
        while True:
            try:
                from langgraph_runtime_postgres_py.database import _get_pool
                pool = await _get_pool()
                async with pool.connection() as conn:
                    await conn.execute(
                        "UPDATE worker_registry SET status = 'dead' "
                        "WHERE last_heartbeat < NOW() - INTERVAL '%s seconds'",
                        (STALE_WORKER_TIMEOUT_SECS,),
                    )
                # Reclaim stale messages
                await redis.xautoclaim(
                    RUNS_STREAM, CONSUMER_GROUP, consumer_name,
                    min_idle_time=STALE_WORKER_TIMEOUT_SECS * 1000,
                )
            except Exception:
                pass
            await asyncio.sleep(STALE_WORKER_TIMEOUT_SECS)

    heartbeat_task = asyncio.create_task(heartbeat_loop())
    sweep_task = asyncio.create_task(sweep_stale_workers())

    try:
        while True:
            try:
                messages = await redis.xreadgroup(
                    groupname=CONSUMER_GROUP,
                    consumername=consumer_name,
                    streams={RUNS_STREAM: ">"},
                    count=max(1, concurrency - len(active_tasks)),
                    block=5000,
                )
                for stream_name, entries in messages:
                    for msg_id, data in entries:
                        await sem.acquire()
                        run_id = data.get("run_id", b"").decode() if isinstance(data.get("run_id"), bytes) else data.get("run_id", "")
                        task = asyncio.create_task(
                            _execute_run(run_id, run_worker)
                        )
                        task.add_done_callback(lambda t, mid=msg_id: sem.release())
                        task.add_done_callback(partial(on_run_done, msg_id=msg_id))
                        active_tasks.add(task)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("consume loop error", worker_id=worker_id)
                await asyncio.sleep(1)
    finally:
        heartbeat_task.cancel()
        sweep_task.cancel()
        if active_tasks:
            await asyncio.gather(*active_tasks, return_exceptions=True)


async def _execute_run(run_id: str, run_worker) -> Any:
    from langgraph_runtime_postgres_py.database import connect
    async with connect() as conn:
        from langgraph_runtime_postgres_py.ops import Runs
        run = await Runs.get(conn, run_id=run_id)
        return await run_worker(run, attempt=run.get("attempt", 1))
