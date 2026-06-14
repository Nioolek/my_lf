# LangGraph Runtime Postgres — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `langgraph_runtime_postgres` — a production-grade runtime backend that replaces `langgraph_runtime_inmem` with Postgres persistence and Redis distributed queuing.

**Architecture:** New package at `src/langgraph_runtime_postgres/` implementing the 8-module runtime contract. Checkpointer bridges to existing `langgraph-checkpoint-postgres`. Ops layer uses psycopg3 async SQL. Queue uses Redis Streams + Consumer Groups. Store uses PG KV + pgvector. Modified `langgraph_api` files for SSE keep-alive and event hooks are minimal and additive.

**Tech Stack:** Python 3.13, psycopg3 (async), Redis (hiredis), pgvector, langgraph-checkpoint-postgres, langgraph-checkpoint-conformance

---

## File Structure

```
src/langgraph_runtime_postgres/          # NEW — 13 source files
├── __init__.py                          # Package version + module exposure
├── database.py                          # psycopg3 pool, migration runner, connect(), healthcheck()
├── ops.py                               # PG SQL CRUD: Assistants, Threads, Runs, Crons
├── checkpoint.py                        # Thin bridge to AsyncPostgresSaver
├── store.py                             # PG KV store + pgvector (optional)
├── queue.py                             # Redis Streams consumer group queue
├── events.py                            # Redis Pub/Sub event bus
├── lifespan.py                          # Startup/shutdown orchestration
├── metrics.py                           # Worker + DB pool metrics
├── retry.py                             # psycopg3 retry decorator
├── routes.py                            # Internal management routes
├── sse_keepalive.py                     # SSE interrupt keep-alive patch
├── worker_process.py                    # Standalone worker entry point
├── migrations/
│   ├── 001_initial_ops.sql              # Ops tables + worker_registry
│   └── 002_store.sql                    # KV + vector tables
└── tests/
    ├── conftest.py                       # PG + Redis testcontainers fixtures
    ├── test_database.py                  # Pool, migration, healthcheck
    ├── test_ops.py                       # CRUD round-trips, search, pagination
    ├── test_queue.py                     # Enqueue → consume → ack cycle
    ├── test_store.py                     # KV ops, vector search, TTL
    ├── test_checkpoint.py                # Conformance suite validation
    ├── test_events.py                    # Publish/subscribe flow
    └── test_integration.py              # End-to-end: thread → run → stream

src/langgraph_api/                       # MODIFIED — 3 files
├── sse.py                               # +50 lines: interrupt keep-alive
├── worker.py                            # +30 lines: event emission hooks
└── stream.py                            # +40 lines: interrupt detection in astream_state
```

---

### Task 1: Package Skeleton + Dependencies

**Files:**
- Create: `src/langgraph_runtime_postgres/__init__.py`
- Create: `src/langgraph_runtime_postgres/pyproject.toml`

- [ ] **Step 1: Create `__init__.py`**

```python
"""LangGraph Postgres Runtime — Production-grade runtime backend.

Activate with::

    export LANGGRAPH_RUNTIME_EDITION=postgres
    export DATABASE_URI=postgresql://user:pass@localhost:5432/langgraph
    export REDIS_URI=redis://localhost:6379
"""

__version__ = "0.1.0"
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[project]
name = "langgraph-runtime-postgres"
version = "0.1.0"
description = "Postgres + Redis runtime backend for LangGraph API"
requires-python = ">=3.13"
dependencies = [
    "langgraph-api>=0.10.0",
    "langgraph-checkpoint-postgres>=3.1.0",
    "psycopg[binary]>=3.2.0",
    "psycopg-pool>=3.2.0",
    "redis[hiredis]>=5.0.0",
    "pgvector>=0.3.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "testcontainers>=4.0",
]
```

- [ ] **Step 3: Verify package is importable**

Run: `source .venv/Scripts/activate && python -c "import sys; sys.path.insert(0, 'src'); import langgraph_runtime_postgres; print(langgraph_runtime_postgres.__version__)"`
Expected: `0.1.0`

- [ ] **Step 4: Commit**

```bash
git add src/langgraph_runtime_postgres/__init__.py src/langgraph_runtime_postgres/pyproject.toml
git commit -m "feat: add langgraph-runtime-postgres package skeleton"
```

---

### Task 2: Database Module — Connection Pool + Migration Runner

**Files:**
- Create: `src/langgraph_runtime_postgres/database.py`
- Create: `src/langgraph_runtime_postgres/migrations/001_initial_ops.sql`
- Create: `src/langgraph_runtime_postgres/migrations/002_store.sql`

- [ ] **Step 1: Create migration SQL — `migrations/001_initial_ops.sql`**

```sql
CREATE TABLE IF NOT EXISTS runtime_migrations (v INTEGER PRIMARY KEY);

CREATE TABLE assistants (
    assistant_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    graph_id TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    description TEXT,
    config JSONB NOT NULL DEFAULT '{}',
    context JSONB NOT NULL DEFAULT '{}',
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_assistants_graph_id ON assistants(graph_id);

CREATE TABLE assistant_versions (
    assistant_id UUID NOT NULL REFERENCES assistants(assistant_id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    graph_id TEXT NOT NULL,
    config JSONB NOT NULL DEFAULT '{}',
    context JSONB NOT NULL DEFAULT '{}',
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    name TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (assistant_id, version)
);

CREATE TABLE threads (
    thread_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    metadata JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'idle',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_threads_status ON threads(status);
CREATE INDEX IF NOT EXISTS idx_threads_updated_at ON threads(updated_at);

CREATE TABLE runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id UUID NOT NULL REFERENCES threads(thread_id) ON DELETE CASCADE,
    assistant_id UUID NOT NULL REFERENCES assistants(assistant_id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending',
    kwargs JSONB NOT NULL DEFAULT '{}',
    result JSONB,
    multitask_strategy TEXT NOT NULL DEFAULT 'reject',
    metadata JSONB NOT NULL DEFAULT '{}',
    attempt INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_runs_thread_id ON runs(thread_id);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at);

CREATE TABLE run_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    span_id UUID NOT NULL,
    event TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    tags JSONB NOT NULL DEFAULT '[]',
    data JSONB NOT NULL DEFAULT '{}',
    metadata JSONB NOT NULL DEFAULT '{}',
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_run_events_run_id ON run_events(run_id);

CREATE TABLE crons (
    cron_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assistant_id UUID NOT NULL REFERENCES assistants(assistant_id) ON DELETE CASCADE,
    thread_id UUID REFERENCES threads(thread_id) ON DELETE SET NULL,
    name TEXT NOT NULL DEFAULT '',
    schedule TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}',
    next_run_date TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_crons_next_run ON crons(next_run_date) WHERE next_run_date IS NOT NULL;

CREATE TABLE worker_registry (
    worker_id TEXT PRIMARY KEY,
    hostname TEXT NOT NULL,
    pid INTEGER NOT NULL,
    capacity INTEGER NOT NULL DEFAULT 1,
    active_jobs INTEGER NOT NULL DEFAULT 0,
    last_heartbeat TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status TEXT NOT NULL DEFAULT 'active',
    metadata JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_worker_heartbeat ON worker_registry(last_heartbeat);
```

- [ ] **Step 2: Create migration SQL — `migrations/002_store.sql`**

```sql
CREATE TABLE store_kv (
    namespace TEXT NOT NULL,
    key TEXT NOT NULL,
    value JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    PRIMARY KEY (namespace, key)
);
CREATE INDEX IF NOT EXISTS idx_store_kv_expires ON store_kv(expires_at) WHERE expires_at IS NOT NULL;
```

- [ ] **Step 3: Create `database.py`**

```python
"""Postgres connection pool and migration management."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import structlog
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

if TYPE_CHECKING:
    from langgraph_api.utils import AsyncConnectionProto

logger = structlog.stdlib.get_logger(__name__)

_pool: AsyncConnectionPool | None = None
MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "migrations")


class PgConnectionProto:
    """Adapter that wraps a psycopg AsyncConnection to match the
    AsyncConnectionProto interface expected by ops and api layers."""

    def __init__(self, conn: AsyncConnection):
        self.conn = conn
        self.can_execute = True

    async def execute(self, query: str, *args, **kwargs):
        async with self.conn.cursor() as cur:
            await cur.execute(query, *args, **kwargs)
            try:
                return await cur.fetchall()
            except Exception:
                return None

    @asynccontextmanager
    async def pipeline(self):
        async with self.conn.pipeline():
            yield


async def _get_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        from langgraph_api import config as api_config
        uri = api_config.DATABASE_URI
        if not uri:
            raise RuntimeError(
                "DATABASE_URI is required for langgraph_runtime_postgres. "
                "Set DATABASE_URI=postgresql://user:pass@host:5432/db"
            )
        _pool = AsyncConnectionPool(
            conninfo=uri,
            max_size=api_config.POSTGRES_POOL_MAX_SIZE,
            kwargs={"row_factory": dict_row},
        )
        await _pool.open()
        await _pool.wait()
    return _pool


async def _run_migrations() -> None:
    pool = await _get_pool()
    async with pool.connection() as conn:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS runtime_migrations (v INTEGER PRIMARY KEY)"
        )
        current = await conn.execute(
            "SELECT COALESCE(MAX(v), 0) FROM runtime_migrations"
        )
        current_version = (await current.fetchone())["coalesce"]

        files = sorted(
            f for f in os.listdir(MIGRATIONS_DIR) if f.endswith(".sql")
        )
        for fname in files:
            version = int(fname.split("_")[0])
            if version > current_version:
                path = os.path.join(MIGRATIONS_DIR, fname)
                with open(path) as f:
                    sql = f.read()
                async with conn.cursor() as cur:
                    await cur.execute(sql)
                await conn.execute(
                    "INSERT INTO runtime_migrations (v) VALUES (%s) ON CONFLICT DO NOTHING",
                    (version,),
                )
                logger.info("applied migration", version=version, file=fname)


async def start_pool() -> None:
    await _get_pool()
    await _run_migrations()
    logger.info("postgres pool started")


async def stop_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("postgres pool stopped")


async def healthcheck(*, check_db: bool = True) -> None:
    if check_db:
        pool = await _get_pool()
        async with pool.connection() as conn:
            await conn.execute("SELECT 1")


def pool_stats() -> dict[str, dict[str, int]]:
    if _pool is None:
        return {"pool": {"size": 0, "available": 0, "checked_out": 0}}
    stats = _pool.get_stats()
    return {
        "pool": {
            "size": stats.get("pool_size", 0),
            "available": stats.get("pool_available", 0),
            "checked_out": stats.get("requests_waiting", 0),
        }
    }


@asynccontextmanager
async def connect(
    *, supports_core_api: bool = False, __test__: bool = False
) -> AsyncIterator["AsyncConnectionProto"]:
    pool = await _get_pool()
    async with pool.connection() as conn:
        yield PgConnectionProto(conn)
```

- [ ] **Step 4: Verify module imports**

Run: `source .venv/Scripts/activate && python -c "import sys; sys.path.insert(0, 'src'); from langgraph_runtime_postgres import database; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add src/langgraph_runtime_postgres/database.py src/langgraph_runtime_postgres/migrations/
git commit -m "feat: add database module with connection pool and migrations"
```

---

### Task 3: Checkpoint Bridge

**Files:**
- Create: `src/langgraph_runtime_postgres/checkpoint.py`

- [ ] **Step 1: Create `checkpoint.py`**

```python
"""Bridge to langgraph-checkpoint-postgres AsyncPostgresSaver."""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from langgraph_runtime_postgres.database import _get_pool

_checkpointer: AsyncPostgresSaver | None = None


def Checkpointer(*args: Any, unpack_hook: Any = None, **kwargs: Any) -> AsyncPostgresSaver:
    """Return the singleton AsyncPostgresSaver instance."""
    global _checkpointer
    if _checkpointer is None:
        pool = None
        raise RuntimeError(
            "Checkpointer not initialized. "
            "Call start_checkpointer() during lifespan startup."
        )
    # Delta channel support: if unpack_hook is provided, create a fresh
    # saver that shares the underlying pool but uses custom deserialization.
    if unpack_hook is not None:
        from langgraph_api.serde import Serializer
        return AsyncPostgresSaver(
            conn=_checkpointer.conn,
            serde=Serializer(__unpack_ext_hook__=unpack_hook),
        )
    return _checkpointer


async def start_checkpointer() -> None:
    """Initialize the checkpointer and ensure checkpoint tables exist."""
    global _checkpointer
    pool = await _get_pool()
    _checkpointer = AsyncPostgresSaver(conn=pool)
    await _checkpointer.setup()


async def exit_checkpointer() -> None:
    """Release checkpointer resources."""
    global _checkpointer
    _checkpointer = None


__all__ = ["Checkpointer", "start_checkpointer", "exit_checkpointer"]
```

- [ ] **Step 2: Verify import**

Run: `source .venv/Scripts/activate && python -c "import sys; sys.path.insert(0, 'src'); from langgraph_runtime_postgres import checkpoint; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/langgraph_runtime_postgres/checkpoint.py
git commit -m "feat: add checkpoint bridge to AsyncPostgresSaver"
```

---

### Task 4: Retry + Metrics Modules (Thin Wrappers)

**Files:**
- Create: `src/langgraph_runtime_postgres/retry.py`
- Create: `src/langgraph_runtime_postgres/metrics.py`

- [ ] **Step 1: Create `retry.py`**

```python
"""psycopg3 retry logic."""

from __future__ import annotations

import asyncio
import functools

from psycopg import OperationalError, InterfaceError

RETRIABLE_EXCEPTIONS = (OperationalError, InterfaceError, ConnectionError)
OVERLOADED_EXCEPTIONS = ()


def retry_db(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        for i in range(3):
            if i == 2:
                return await func(*args, **kwargs)
            try:
                return await func(*args, **kwargs)
            except RETRIABLE_EXCEPTIONS:
                await asyncio.sleep(0.1 * (2 ** i))
    return wrapper
```

- [ ] **Step 2: Create `metrics.py`**

```python
"""Runtime metrics."""

from __future__ import annotations

from langgraph_runtime_postgres.database import pool_stats


def get_metrics() -> dict[str, dict[str, int]]:
    from langgraph_api import config as api_config
    workers_max = api_config.N_JOBS_PER_WORKER
    db_stats = pool_stats()
    return {
        "workers": {
            "max": workers_max,
            "active": 0,  # Updated by queue heartbeat
            "available": workers_max,
        },
        **db_stats,
    }
```

- [ ] **Step 3: Commit**

```bash
git add src/langgraph_runtime_postgres/retry.py src/langgraph_runtime_postgres/metrics.py
git commit -m "feat: add retry and metrics modules"
```

---

### Task 5: Events Module — Redis Pub/Sub Event Bus

**Files:**
- Create: `src/langgraph_runtime_postgres/events.py`

- [ ] **Step 1: Create `events.py`**

```python
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
    from langgraph_runtime_postgres.queue import get_redis
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
```

- [ ] **Step 2: Commit**

```bash
git add src/langgraph_runtime_postgres/events.py
git commit -m "feat: add Redis Pub/Sub event bus"
```

---

### Task 6: Queue Module — Redis Streams Distributed Queue

**Files:**
- Create: `src/langgraph_runtime_postgres/queue.py`

- [ ] **Step 1: Create `queue.py`**

```python
"""Redis Streams + Consumer Groups distributed task queue."""

from __future__ import annotations

import asyncio
import json
import os
import socket
from datetime import UTC, datetime
from functools import partial
from typing import TYPE_CHECKING
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
                "REDIS_URI is required for langgraph_runtime_postgres queue. "
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
    from langgraph_runtime_postgres.events import EventType, publish_event

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
                from langgraph_runtime_postgres.database import _get_pool
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
                from langgraph_runtime_postgres.database import _get_pool
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
    from langgraph_runtime_postgres.database import connect
    async with connect() as conn:
        from langgraph_runtime_postgres.ops import Runs
        run = await Runs.get(conn, run_id=run_id)
        return await run_worker(run, attempt=run.get("attempt", 1))
```

- [ ] **Step 2: Commit**

```bash
git add src/langgraph_runtime_postgres/queue.py
git commit -m "feat: add Redis Streams distributed queue"
```

---

### Task 7: Ops Module — Postgres CRUD

**Files:**
- Create: `src/langgraph_runtime_postgres/ops.py`

This is the largest file. Reference: `src/langgraph_runtime_inmem/ops.py` for exact interface signatures.

- [ ] **Step 1: Create `ops.py` — imports and helpers**

```python
"""Postgres CRUD operations for Assistants, Threads, Runs, and Crons.

Interface matches langgraph_runtime_inmem/ops.py exactly.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import structlog
from psycopg.rows import dict_row
from starlette.exceptions import HTTPException

from langgraph_runtime_postgres.database import connect as db_connect
from langgraph_runtime_postgres.retry import retry_db

logger = structlog.stdlib.get_logger(__name__)

# ---- Helpers ----

def _ensure_uuid(id_: str | UUID | None) -> UUID:
    if isinstance(id_, str):
        return UUID(id_)
    if id_ is None:
        return uuid4()
    return id_

def _to_uuid_str(v: Any) -> str | None:
    if v is None:
        return None
    return str(v)

def _now_iso() -> str:
    return datetime.now(UTC).isoformat()

def _row_to_dict(row: dict) -> dict:
    """Convert a dict_row result to a plain dict with string keys."""
    return {k: str(v) if isinstance(v, UUID) else v for k, v in row.items()}
```

- [ ] **Step 2: Append `Authenticated` base class**

```python
class Authenticated:
    """Base class providing auth context access."""
    pass
```

- [ ] **Step 3: Append `Assistants` class**

```python
class Assistants(Authenticated):
    @staticmethod
    async def create(
        conn,
        *,
        graph_id: str,
        config: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        name: str = "",
        description: str | None = None,
    ) -> dict:
        config = config or {}
        context = context or {}
        metadata = metadata or {}
        row = await conn.execute(
            """INSERT INTO assistants (graph_id, name, description, config, context, metadata)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING *""",
            (graph_id, name, description, json.dumps(config), json.dumps(context), json.dumps(metadata)),
        )
        return dict(row[0])

    @staticmethod
    async def get(conn, *, assistant_id: str | UUID) -> dict | None:
        rows = await conn.execute(
            "SELECT * FROM assistants WHERE assistant_id = %s",
            (str(assistant_id),),
        )
        if rows:
            return dict(rows[0])
        raise HTTPException(status_code=404, detail="Assistant not found")

    @staticmethod
    async def update(
        conn,
        *,
        assistant_id: str | UUID,
        graph_id: str | None = None,
        config: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        name: str | None = None,
        description: str | None = None,
    ) -> dict:
        current = await Assistants.get(conn, assistant_id=assistant_id)
        # Record version history
        await conn.execute(
            """INSERT INTO assistant_versions (assistant_id, version, graph_id, config, context, metadata, name)
               VALUES (%s, COALESCE((SELECT MAX(version) FROM assistant_versions WHERE assistant_id=%s), 0) + 1,
                       %s, %s, %s, %s, %s)""",
            (str(assistant_id), str(assistant_id), current["graph_id"],
             json.dumps(current.get("config", {})), json.dumps(current.get("context", {})),
             json.dumps(current.get("metadata", {})), current.get("name", "")),
        )
        sets = []
        params: list[Any] = []
        if graph_id is not None:
            sets.append("graph_id = %s"); params.append(graph_id)
        if config is not None:
            sets.append("config = %s"); params.append(json.dumps(config))
        if context is not None:
            sets.append("context = %s"); params.append(json.dumps(context))
        if metadata is not None:
            sets.append("metadata = %s"); params.append(json.dumps(metadata))
        if name is not None:
            sets.append("name = %s"); params.append(name)
        if description is not None:
            sets.append("description = %s"); params.append(description)
        sets.append("updated_at = NOW()")
        params.append(str(assistant_id))
        rows = await conn.execute(
            f"UPDATE assistants SET {', '.join(sets)} WHERE assistant_id = %s RETURNING *",
            params,
        )
        return dict(rows[0])

    @staticmethod
    async def search(
        conn,
        *,
        graph_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[dict]:
        wheres = ["1=1"]
        params: list[Any] = []
        if graph_id is not None:
            wheres.append("graph_id = %s"); params.append(graph_id)
        if metadata:
            wheres.append("metadata @> %s"); params.append(json.dumps(metadata))
        params.extend([limit, offset])
        rows = await conn.execute(
            f"SELECT * FROM assistants WHERE {' AND '.join(wheres)} ORDER BY created_at DESC LIMIT %s OFFSET %s",
            params,
        )
        return [dict(r) for r in rows]

    @staticmethod
    async def delete(conn, *, assistant_id: str | UUID) -> None:
        await conn.execute("DELETE FROM assistants WHERE assistant_id = %s", (str(assistant_id),))

    @staticmethod
    async def versions(
        conn, *, assistant_id: str | UUID, limit: int = 10, offset: int = 0
    ) -> list[dict]:
        rows = await conn.execute(
            "SELECT * FROM assistant_versions WHERE assistant_id = %s ORDER BY version DESC LIMIT %s OFFSET %s",
            (str(assistant_id), limit, offset),
        )
        return [dict(r) for r in rows]
```

- [ ] **Step 4: Append `Threads` class**

```python
class Threads(Authenticated):
    @staticmethod
    async def create(
        conn,
        *,
        thread_id: str | UUID | None = None,
        metadata: dict[str, Any] | None = None,
        if_not_exists: str | None = None,
    ) -> dict:
        tid = str(thread_id) if thread_id else str(uuid4())
        metadata = metadata or {}
        rows = await conn.execute(
            """INSERT INTO threads (thread_id, metadata, status)
               VALUES (%s, %s, 'idle')
               ON CONFLICT (thread_id) DO UPDATE SET metadata = threads.metadata
               RETURNING *""",
            (tid, json.dumps(metadata)),
        )
        return dict(rows[0])

    @staticmethod
    async def get(conn, *, thread_id: str | UUID) -> dict | None:
        rows = await conn.execute(
            "SELECT * FROM threads WHERE thread_id = %s", (str(thread_id),),
        )
        if rows:
            return dict(rows[0])
        raise HTTPException(status_code=404, detail="Thread not found")

    @staticmethod
    async def update(
        conn,
        *,
        thread_id: str | UUID,
        metadata: dict[str, Any] | None = None,
        status: str | None = None,
    ) -> dict:
        sets = ["updated_at = NOW()"]
        params: list[Any] = []
        if metadata is not None:
            sets.append("metadata = %s"); params.append(json.dumps(metadata))
        if status is not None:
            sets.append("status = %s"); params.append(status)
        params.append(str(thread_id))
        rows = await conn.execute(
            f"UPDATE threads SET {', '.join(sets)} WHERE thread_id = %s RETURNING *",
            params,
        )
        return dict(rows[0])

    @staticmethod
    async def search(
        conn,
        *,
        metadata: dict[str, Any] | None = None,
        values: dict[str, Any] | None = None,
        status: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[dict]:
        wheres = ["1=1"]
        params: list[Any] = []
        if metadata:
            wheres.append("metadata @> %s"); params.append(json.dumps(metadata))
        if status is not None:
            wheres.append("status = %s"); params.append(status)
        params.extend([limit, offset])
        rows = await conn.execute(
            f"SELECT * FROM threads WHERE {' AND '.join(wheres)} ORDER BY updated_at DESC LIMIT %s OFFSET %s",
            params,
        )
        return [dict(r) for r in rows]

    @staticmethod
    async def delete(conn, *, thread_id: str | UUID) -> None:
        await conn.execute("DELETE FROM threads WHERE thread_id = %s", (str(thread_id),))

    @staticmethod
    async def get_state(
        conn,
        *,
        thread_id: str | UUID,
        checkpoint_ns: str = "",
        subgraphs: bool = False,
    ) -> Any:
        from langgraph_runtime_postgres.checkpoint import Checkpointer
        checkpointer = Checkpointer()
        config = {"configurable": {"thread_id": str(thread_id), "checkpoint_ns": checkpoint_ns}}
        tup = await checkpointer.aget_tuple(config)
        if tup is None:
            raise HTTPException(status_code=404, detail="No state found for thread")
        from langgraph.pregel.debug import StateSnapshot
        return StateSnapshot(
            values=tup.checkpoint.get("channel_values", {}),
            next=tuple(tup.checkpoint.get("channel_versions", {}).keys()),
            config=tup.config,
            metadata=tup.metadata,
            created_at=tup.checkpoint.get("ts"),
            parent_config=tup.parent_config,
            tasks=tup.pending_writes or [],
        )

    @staticmethod
    async def update_state(
        conn,
        *,
        thread_id: str | UUID,
        values: dict[str, Any],
        as_node: str | None = None,
        checkpoint_id: str | None = None,
    ) -> dict:
        from langgraph_runtime_postgres.checkpoint import Checkpointer
        checkpointer = Checkpointer()
        config = {"configurable": {"thread_id": str(thread_id)}}
        if checkpoint_id:
            config["configurable"]["checkpoint_id"] = checkpoint_id
        return await checkpointer.aput(
            config,
            {"channel_values": values, "channel_versions": {}, "versions_seen": {}, "id": str(uuid4()), "v": 1, "ts": _now_iso()},
            {"source": "update", "step": 0},
            {},
        )

    @staticmethod
    async def get_history(
        conn,
        *,
        thread_id: str | UUID,
        limit: int = 10,
        before: Any = None,
        checkpoint_ns: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> list[Any]:
        from langgraph_runtime_postgres.checkpoint import Checkpointer
        checkpointer = Checkpointer()
        config = {"configurable": {"thread_id": str(thread_id), "checkpoint_ns": checkpoint_ns}}
        filter_dict = metadata or {}
        results = []
        async for tup in checkpointer.alist(config, filter=filter_dict, before=before, limit=limit):
            from langgraph.pregel.debug import StateSnapshot
            results.append(StateSnapshot(
                values=tup.checkpoint.get("channel_values", {}),
                next=tuple(tup.checkpoint.get("channel_versions", {}).keys()),
                config=tup.config,
                metadata=tup.metadata,
                created_at=tup.checkpoint.get("ts"),
                parent_config=tup.parent_config,
                tasks=tup.pending_writes or [],
            ))
        return results
```

- [ ] **Step 5: Append `Runs` class**

```python
class Runs(Authenticated):
    @staticmethod
    async def create(
        conn,
        *,
        thread_id: str | UUID,
        assistant_id: str | UUID,
        run_id: str | UUID | None = None,
        kwargs: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        multitask_strategy: str = "reject",
        if_not_exists: str | None = None,
    ) -> dict:
        rid = str(run_id) if run_id else str(uuid4())
        kwargs = kwargs or {}
        metadata = metadata or {}
        rows = await conn.execute(
            """INSERT INTO runs (run_id, thread_id, assistant_id, kwargs, metadata, multitask_strategy, status)
               VALUES (%s, %s, %s, %s, %s, %s, 'pending') RETURNING *""",
            (rid, str(thread_id), str(assistant_id), json.dumps(kwargs), json.dumps(metadata), multitask_strategy),
        )
        return dict(rows[0])

    @staticmethod
    async def get(conn, *, run_id: str | UUID) -> dict | None:
        rows = await conn.execute(
            "SELECT * FROM runs WHERE run_id = %s", (str(run_id),),
        )
        if rows:
            return dict(rows[0])
        raise HTTPException(status_code=404, detail="Run not found")

    @staticmethod
    async def search(
        conn,
        *,
        thread_id: str | UUID | None = None,
        status: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[dict]:
        wheres = ["1=1"]
        params: list[Any] = []
        if thread_id is not None:
            wheres.append("thread_id = %s"); params.append(str(thread_id))
        if status is not None:
            wheres.append("status = %s"); params.append(status)
        params.extend([limit, offset])
        rows = await conn.execute(
            f"SELECT * FROM runs WHERE {' AND '.join(wheres)} ORDER BY created_at DESC LIMIT %s OFFSET %s",
            params,
        )
        return [dict(r) for r in rows]

    @staticmethod
    async def update(
        conn,
        *,
        run_id: str | UUID,
        status: str | None = None,
        result: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        attempt: int | None = None,
    ) -> dict:
        sets = ["updated_at = NOW()"]
        params: list[Any] = []
        if status is not None:
            sets.append("status = %s"); params.append(status)
        if result is not None:
            sets.append("result = %s"); params.append(json.dumps(result))
        if metadata is not None:
            sets.append("metadata = %s"); params.append(json.dumps(metadata))
        if attempt is not None:
            sets.append("attempt = %s"); params.append(attempt)
        params.append(str(run_id))
        rows = await conn.execute(
            f"UPDATE runs SET {', '.join(sets)} WHERE run_id = %s RETURNING *",
            params,
        )
        if rows:
            return dict(rows[0])
        raise HTTPException(status_code=404, detail="Run not found")

    @staticmethod
    async def delete(conn, *, run_id: str | UUID) -> None:
        await conn.execute("DELETE FROM runs WHERE run_id = %s", (str(run_id),))

    @staticmethod
    async def next(
        *,
        wait: bool = True,
        limit: int = 1,
    ) -> AsyncIterator[tuple[dict, int]]:
        """Poll pending runs. In postgres runtime, runs are consumed via Redis Streams.
        This method is kept for the cron scheduler and internal sweepers."""
        async with db_connect() as conn:
            while True:
                rows = await conn.execute(
                    "SELECT * FROM runs WHERE status = 'pending' ORDER BY created_at ASC LIMIT %s FOR UPDATE SKIP LOCKED",
                    (limit,),
                )
                for row in (rows or []):
                    r = dict(row)
                    await Runs.update(conn, run_id=r["run_id"], status="running")
                    yield r, r.get("attempt", 1)
                if not wait:
                    break
                await asyncio.sleep(1)

    @staticmethod
    async def stats(conn) -> dict:
        rows = await conn.execute(
            "SELECT status, COUNT(*) as count FROM runs GROUP BY status"
        )
        return {r["status"]: r["count"] for r in rows}

    @staticmethod
    async def sweep() -> None:
        """Mark stale runs as timed out."""
        async with db_connect() as conn:
            await conn.execute(
                "UPDATE runs SET status = 'timeout', updated_at = NOW() "
                "WHERE status = 'running' AND updated_at < NOW() - INTERVAL '%s seconds'",
                (STALE_RUN_TIMEOUT_SECS,),
            )
```

- [ ] **Step 6: Append `Crons` class**

```python
class Crons(Authenticated):
    @staticmethod
    async def create(
        conn,
        *,
        assistant_id: str | UUID,
        schedule: str,
        payload: dict[str, Any] | None = None,
        thread_id: str | UUID | None = None,
        name: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        payload = payload or {}
        metadata = metadata or {}
        import croniter as croniter_mod
        cron = croniter_mod.croniter(schedule, datetime.now(UTC))
        next_run = cron.get_next(datetime)
        rows = await conn.execute(
            """INSERT INTO crons (assistant_id, thread_id, schedule, payload, name, metadata, next_run_date)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *""",
            (str(assistant_id), str(thread_id) if thread_id else None, schedule,
             json.dumps(payload), name, json.dumps(metadata), next_run),
        )
        return dict(rows[0])

    @staticmethod
    async def get(conn, *, cron_id: str | UUID) -> dict:
        rows = await conn.execute("SELECT * FROM crons WHERE cron_id = %s", (str(cron_id),))
        if rows:
            return dict(rows[0])
        raise HTTPException(status_code=404, detail="Cron not found")

    @staticmethod
    async def search(
        conn,
        *,
        assistant_id: str | UUID | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[dict]:
        wheres = ["1=1"]
        params: list[Any] = []
        if assistant_id is not None:
            wheres.append("assistant_id = %s"); params.append(str(assistant_id))
        params.extend([limit, offset])
        rows = await conn.execute(
            f"SELECT * FROM crons WHERE {' AND '.join(wheres)} ORDER BY created_at DESC LIMIT %s OFFSET %s",
            params,
        )
        return [dict(r) for r in rows]

    @staticmethod
    async def delete(conn, *, cron_id: str | UUID) -> None:
        await conn.execute("DELETE FROM crons WHERE cron_id = %s", (str(cron_id),))

    @staticmethod
    async def next(conn) -> AsyncIterator[dict]:
        rows = await conn.execute(
            "SELECT * FROM crons WHERE next_run_date <= NOW() ORDER BY next_run_date ASC LIMIT 10"
        )
        for r in (rows or []):
            yield dict(r)

    @staticmethod
    async def set_next_run_date(conn, *, cron_id: str | UUID, next_run_date: Any) -> None:
        await conn.execute(
            "UPDATE crons SET next_run_date = %s, updated_at = NOW() WHERE cron_id = %s",
            (next_run_date, str(cron_id)),
        )
```

- [ ] **Step 7: Append `RunEvents` class**

```python
class RunEvents:
    @staticmethod
    async def create(
        conn,
        *,
        run_id: str | UUID,
        span_id: str | UUID,
        event: str,
        name: str = "",
        tags: list[str] | None = None,
        data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        tags = tags or []
        data = data or {}
        metadata = metadata or {}
        rows = await conn.execute(
            """INSERT INTO run_events (run_id, span_id, event, name, tags, data, metadata)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *""",
            (str(run_id), str(span_id), event, name, json.dumps(tags), json.dumps(data), json.dumps(metadata)),
        )
        return dict(rows[0])

    @staticmethod
    async def search(
        conn,
        *,
        run_id: str | UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        rows = await conn.execute(
            "SELECT * FROM run_events WHERE run_id = %s ORDER BY received_at ASC LIMIT %s OFFSET %s",
            (str(run_id), limit, offset),
        )
        return [dict(r) for r in rows]
```

- [ ] **Step 8: Verify import**

Run: `source .venv/Scripts/activate && python -c "import sys; sys.path.insert(0, 'src'); from langgraph_runtime_postgres import ops; print('OK')"`
Expected: `OK`

- [ ] **Step 9: Commit**

```bash
git add src/langgraph_runtime_postgres/ops.py
git commit -m "feat: add Postgres ops CRUD (Assistants, Threads, Runs, Crons, RunEvents)"
```

---

### Task 8: Store Module — PG KV + pgvector

**Files:**
- Create: `src/langgraph_runtime_postgres/store.py`

- [ ] **Step 1: Create `store.py`**

```python
"""Postgres-backed key-value store with optional pgvector support."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

import structlog
from langgraph.store.base import BaseStore, Op, Result
from langgraph.store.base.batch import AsyncBatchedBaseStore

logger = structlog.stdlib.get_logger(__name__)

_STORE_CONFIG: dict[str, Any] | None = None
STORE: "PgStore | None" = None


def set_store_config(config: dict[str, Any] | None) -> None:
    global _STORE_CONFIG
    _STORE_CONFIG = config


class PgStore(AsyncBatchedBaseStore):
    """Postgres-backed key-value store."""

    def __init__(self) -> None:
        super().__init__()

    async def abatch(self, ops: Iterable[Op]) -> list[Result]:
        from langgraph_runtime_postgres.database import _get_pool
        pool = await _get_pool()
        results: list[Result] = []

        async with pool.connection() as conn:
            for op in ops:
                namespace = op.namespace
                key = op.key
                path = op.path

                if op.operation == "put":
                    await conn.execute(
                        """INSERT INTO store_kv (namespace, key, value, expires_at)
                           VALUES (%s, %s, %s, %s)
                           ON CONFLICT (namespace, key) DO UPDATE
                           SET value = EXCLUDED.value, updated_at = NOW()""",
                        (namespace, key, json.dumps({"path": path, "value": op.value}),
                         datetime.now(UTC) if op.ttl else None),
                    )
                    results.append(Result(ok=True))
                elif op.operation == "get":
                    rows = await conn.execute(
                        "SELECT value FROM store_kv WHERE namespace = %s AND key = %s",
                        (namespace, key),
                    )
                    if rows:
                        results.append(Result(ok=True, value=rows[0]["value"]))
                    else:
                        results.append(Result(ok=True, value=None))
                elif op.operation == "delete":
                    await conn.execute(
                        "DELETE FROM store_kv WHERE namespace = %s AND key = %s",
                        (namespace, key),
                    )
                    results.append(Result(ok=True))
                elif op.operation == "search":
                    rows = await conn.execute(
                        "SELECT key, value FROM store_kv WHERE namespace = %s AND value @> %s LIMIT %s",
                        (namespace, json.dumps({"path": op.path} if op.path else {}), op.limit or 10),
                    )
                    items = [(r["key"], r["value"]) for r in rows]
                    results.append(Result(ok=True, value=items))
                else:
                    results.append(Result(ok=False, error=f"Unknown op: {op.operation}"))
        return results

    async def start_ttl_sweeper(self) -> None:
        """Background task to delete expired entries."""
        import asyncio
        from langgraph_runtime_postgres.database import _get_pool

        async def _sweep() -> None:
            while True:
                try:
                    pool = await _get_pool()
                    async with pool.connection() as conn:
                        await conn.execute(
                            "DELETE FROM store_kv WHERE expires_at IS NOT NULL AND expires_at < NOW()"
                        )
                except Exception:
                    logger.warning("ttl sweep failed", exc_info=True)
                await asyncio.sleep(60)
        asyncio.create_task(_sweep())


def Store(*args: Any, **kwargs: Any) -> PgStore:
    global STORE
    if STORE is None:
        STORE = PgStore()
    return STORE


async def collect_store_from_env() -> None:
    from langgraph_api import config as api_config
    if api_config.STORE_CONFIG:
        set_store_config(api_config.STORE_CONFIG)


async def get_store() -> PgStore:
    return Store()


async def exit_store() -> None:
    global STORE
    STORE = None
```

- [ ] **Step 2: Commit**

```bash
git add src/langgraph_runtime_postgres/store.py
git commit -m "feat: add Postgres KV store with TTL support"
```

---

### Task 9: Lifespan + Routes + Internal Modules

**Files:**
- Create: `src/langgraph_runtime_postgres/lifespan.py`
- Create: `src/langgraph_runtime_postgres/routes.py`

- [ ] **Step 1: Create `lifespan.py`**

```python
"""Application lifecycle for Postgres runtime."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from starlette.applications import Starlette

logger = structlog.stdlib.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: "Starlette | None" = None, cancel_event=None, taskset=None, **kwargs):
    """Postgres runtime lifecycle."""
    from langgraph_runtime_postgres.database import start_pool, stop_pool
    from langgraph_runtime_postgres.checkpoint import start_checkpointer, exit_checkpointer
    from langgraph_runtime_postgres.store import collect_store_from_env, get_store, exit_store
    from langgraph_runtime_postgres.queue import start_redis, stop_redis, queue
    from langgraph_api import config as api_config
    from langgraph_api import graph
    from langgraph_runtime_inmem.inmem_stream import start_stream, stop_stream
    from langgraph_api.asyncio import SimpleTaskGroup
    from langgraph_api.http import start_http_client, stop_http_client
    from langchain_core.runnables.config import var_child_runnable_config
    from langgraph_api.graph import collect_graphs_from_env
    from langgraph_api.cron_scheduler import cron_scheduler

    # --- Startup ---
    await start_http_client()
    await start_pool()
    await start_checkpointer()
    await start_redis()
    await start_stream()
    await collect_store_from_env()
    store_instance = await get_store()

    # Configure runtime context
    if getattr(api_config, "USE_RUNTIME_CONTEXT_API", False):
        from langgraph.runtime import Runtime
        from langgraph_api.config import CONFIG_KEY_RUNTIME
        langgraph_config = {"configurable": {CONFIG_KEY_RUNTIME: Runtime(store=store_instance)}}
    else:
        from langgraph_api.config import CONFIG_KEY_STORE
        langgraph_config = {"configurable": {CONFIG_KEY_STORE: store_instance}}
    var_child_runnable_config.set(langgraph_config)

    await collect_graphs_from_env(True)

    # --- Background tasks ---
    async with SimpleTaskGroup(cancel=True) as tg:
        if api_config.N_JOBS_PER_WORKER > 0:
            tg.create_task(queue())

        tg.create_task(cron_scheduler())

        yield  # App runs

    # --- Shutdown ---
    await exit_store()
    await exit_checkpointer()
    await stop_stream()
    await stop_redis()
    await stop_http_client()
    await stop_pool()
```

- [ ] **Step 2: Create `routes.py`**

```python
"""Internal management routes."""

from __future__ import annotations

from langgraph_api.route import ApiRoute


async def _truncate(request):
    from langgraph_runtime_postgres.database import _get_pool
    pool = await _get_pool()
    async with pool.connection() as conn:
        for table in ["run_events", "runs", "crons", "threads", "assistant_versions", "assistants", "worker_registry"]:
            await conn.execute(f"DELETE FROM {table}")
    return {"ok": True}


async def _debug_thread(request):
    thread_id = request.path_params["thread_id"]
    from langgraph_runtime_postgres.database import _get_pool
    pool = await _get_pool()
    async with pool.connection() as conn:
        rows = await conn.execute("SELECT * FROM threads WHERE thread_id = %s", (thread_id,))
        thread = dict(rows[0]) if rows else None
        rows = await conn.execute("SELECT * FROM runs WHERE thread_id = %s ORDER BY created_at DESC", (thread_id,))
        runs = [dict(r) for r in rows]
    return {"thread": thread, "runs": runs}


ROUTES = [
    ApiRoute("/internal/truncate", _truncate, methods=["POST"]),
    ApiRoute("/internal/debug/thread/{thread_id}", _debug_thread, methods=["GET"]),
]
```

- [ ] **Step 3: Commit**

```bash
git add src/langgraph_runtime_postgres/lifespan.py src/langgraph_runtime_postgres/routes.py
git commit -m "feat: add lifespan and internal routes"
```

---

### Task 10: SSE Keep-Alive Patch

**Files:**
- Create: `src/langgraph_runtime_postgres/sse_keepalive.py`
- Modify: `src/langgraph_api/sse.py`

- [ ] **Step 1: Create `sse_keepalive.py`**

```python
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
    from langgraph_runtime_postgres.database import _get_pool
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
                from langgraph_runtime_postgres.checkpoint import Checkpointer
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
```

- [ ] **Step 2: Apply the patch in lifespan**

In `src/langgraph_runtime_postgres/lifespan.py`, add to startup:

```python
from langgraph_runtime_postgres.sse_keepalive import apply_sse_patch
apply_sse_patch()
```

- [ ] **Step 3: Commit**

```bash
git add src/langgraph_runtime_postgres/sse_keepalive.py src/langgraph_runtime_postgres/lifespan.py
git commit -m "feat: add SSE interrupt keep-alive patch"
```

---

### Task 11: Worker Event Hooks

**Files:**
- Modify: `src/langgraph_api/worker.py`
- Modify: `src/langgraph_api/stream.py`

- [ ] **Step 1: Add event emission to worker.py**

In `src/langgraph_api/worker.py`, find the `worker` function. After `astream_state` yields events, add event hooks. The modification is additive — add these lines at the start and end of the worker function, and after each stream event:

```python
# At top of worker function, after run is created:
try:
    from langgraph_runtime_postgres.events import EventType, publish_event
    await publish_event(EventType.RUN_STARTED, {
        "run_id": str(run["run_id"]),
        "thread_id": str(run["thread_id"]),
        "assistant_id": str(run.get("assistant_id", "")),
    })
except ImportError:
    pass  # Not using postgres runtime

# After stream completes successfully:
try:
    from langgraph_runtime_postgres.events import EventType, publish_event
    await publish_event(EventType.RUN_COMPLETED, {
        "run_id": str(run["run_id"]),
        "status": "success",
    })
except ImportError:
    pass

# On error:
try:
    from langgraph_runtime_postgres.events import EventType, publish_event
    await publish_event(EventType.RUN_FAILED, {
        "run_id": str(run["run_id"]),
        "error": str(e),
    })
except ImportError:
    pass
```

- [ ] **Step 2: Add interrupt detection to stream.py**

In `src/langgraph_api/stream.py`, in `astream_state`, add interrupt event yielding:

```python
# Inside the event loop in astream_state, add interrupt detection:
if event_type == "interrupt":
    yield ("interrupt", {
        "thread_id": run["thread_id"],
        "run_id": run["run_id"],
        "interrupt_value": event_data,
    })
```

- [ ] **Step 3: Commit**

```bash
git add src/langgraph_api/worker.py src/langgraph_api/stream.py
git commit -m "feat: add worker event hooks and stream interrupt detection"
```

---

### Task 12: Worker Process Entry Point

**Files:**
- Create: `src/langgraph_runtime_postgres/worker_process.py`

- [ ] **Step 1: Create `worker_process.py`**

```python
"""Standalone worker process entry point.

Usage:
    python -m langgraph_runtime_postgres.worker_process
"""

import asyncio
import os
import signal
import sys


async def main() -> None:
    """Start a worker process consuming from Redis Streams."""
    os.environ.setdefault("LANGGRAPH_RUNTIME_EDITION", "postgres")

    from langgraph_runtime_postgres.database import start_pool, stop_pool
    from langgraph_runtime_postgres.checkpoint import start_checkpointer, exit_checkpointer
    from langgraph_runtime_postgres.queue import start_redis, stop_redis, queue
    from langgraph_runtime_postgres.store import collect_store_from_env, get_store, exit_store

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
```

- [ ] **Step 2: Commit**

```bash
git add src/langgraph_runtime_postgres/worker_process.py
git commit -m "feat: add standalone worker process entry point"
```

---

### Task 13: Test Infrastructure + Conformance Validation

**Files:**
- Create: `src/langgraph_runtime_postgres/tests/conftest.py`
- Create: `src/langgraph_runtime_postgres/tests/test_checkpoint.py`

- [ ] **Step 1: Create `tests/conftest.py`**

```python
"""Test fixtures using testcontainers for Postgres + Redis."""

import pytest


@pytest.fixture(scope="session")
def pg_uri():
    from testcontainers.postgres import PostgresContainer
    with PostgresContainer("postgres:16") as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def redis_uri():
    from testcontainers.redis import RedisContainer
    with RedisContainer("redis:7-alpine") as r:
        yield f"redis://{r.get_container_host_ip()}:{r.get_exposed_port(6379)}"


@pytest.fixture(autouse=True)
def setup_env(pg_uri, redis_uri, monkeypatch):
    monkeypatch.setenv("LANGGRAPH_RUNTIME_EDITION", "postgres")
    monkeypatch.setenv("DATABASE_URI", pg_uri)
    monkeypatch.setenv("REDIS_URI", redis_uri)
```

- [ ] **Step 2: Create `tests/test_checkpoint.py`**

```python
"""Validate our checkpointer against the conformance suite."""

import pytest
from langgraph.checkpoint.conformance import checkpointer_test, validate
from langgraph.checkpoint.conformance.report import ProgressCallbacks


@checkpointer_test(name="PostgresRuntimeSaver")
async def pg_runtime_checkpointer():
    from langgraph_runtime_postgres.database import start_pool
    from langgraph_runtime_postgres.checkpoint import start_checkpointer
    await start_pool()
    await start_checkpointer()
    from langgraph_runtime_postgres.checkpoint import Checkpointer
    yield Checkpointer()


@pytest.mark.asyncio
async def test_checkpoint_conformance():
    report = await validate(pg_runtime_checkpointer, progress=ProgressCallbacks.verbose())
    report.print_report()
    assert report.passed_all_base(), f"Base capability tests failed: {report.to_dict()}"
```

- [ ] **Step 3: Run conformance test**

```bash
cd src/langgraph_runtime_postgres && python -m pytest tests/test_checkpoint.py -v
```

- [ ] **Step 4: Commit**

```bash
git add src/langgraph_runtime_postgres/tests/
git commit -m "test: add test infrastructure and conformance validation"
```

---

### Task 14: Integration Test — End-to-End

**Files:**
- Create: `src/langgraph_runtime_postgres/tests/test_integration.py`

- [ ] **Step 1: Create `tests/test_integration.py`**

```python
"""End-to-end integration test: create thread → run → check state."""

import pytest


@pytest.mark.asyncio
async def test_create_thread_and_run(pg_uri, redis_uri):
    from langgraph_runtime_postgres.database import start_pool, connect
    from langgraph_runtime_postgres.ops import Threads, Runs

    await start_pool()

    async with connect() as conn:
        # Create thread
        thread = await Threads.create(conn, metadata={"user": "test"})
        assert thread["thread_id"] is not None
        assert thread["status"] == "idle"
        assert thread["metadata"]["user"] == "test"

        # Create assistant first
        from langgraph_runtime_postgres.ops import Assistants
        assistant = await Assistants.create(
            conn,
            graph_id="test_graph",
            config={"key": "value"},
            name="Test Assistant",
        )
        assert assistant["assistant_id"] is not None

        # Create run
        run = await Runs.create(
            conn,
            thread_id=thread["thread_id"],
            assistant_id=assistant["assistant_id"],
            kwargs={"input": "hello"},
        )
        assert run["status"] == "pending"

        # Search runs
        runs = await Runs.search(conn, thread_id=thread["thread_id"])
        assert len(runs) >= 1

        # Search threads
        threads = await Threads.search(conn, metadata={"user": "test"})
        assert len(threads) >= 1

    from langgraph_runtime_postgres.database import stop_pool
    await stop_pool()


@pytest.mark.asyncio
async def test_assistant_versioning(pg_uri, redis_uri):
    from langgraph_runtime_postgres.database import start_pool, connect
    from langgraph_runtime_postgres.ops import Assistants

    await start_pool()

    async with connect() as conn:
        a = await Assistants.create(conn, graph_id="test", config={"v": 1}, name="Test")
        await Assistants.update(conn, assistant_id=a["assistant_id"], config={"v": 2})
        versions = await Assistants.versions(conn, assistant_id=a["assistant_id"])
        assert len(versions) >= 1  # At least one historical version

    from langgraph_runtime_postgres.database import stop_pool
    await stop_pool()
```

- [ ] **Step 2: Run integration tests**

```bash
cd src/langgraph_runtime_postgres && python -m pytest tests/test_integration.py -v
```

- [ ] **Step 3: Commit**

```bash
git add src/langgraph_runtime_postgres/tests/test_integration.py
git commit -m "test: add end-to-end integration tests"
```

---

## Plan Summary

| Task | Component | Files | Est. Lines |
|------|-----------|-------|-----------|
| 1 | Package skeleton | `__init__.py`, `pyproject.toml` | 25 |
| 2 | Database module | `database.py`, 2 migration SQL | 270 |
| 3 | Checkpoint bridge | `checkpoint.py` | 50 |
| 4 | Retry + Metrics | `retry.py`, `metrics.py` | 55 |
| 5 | Events module | `events.py` | 70 |
| 6 | Queue module | `queue.py` | 180 |
| 7 | Ops module | `ops.py` | 450 |
| 8 | Store module | `store.py` | 120 |
| 9 | Lifespan + Routes | `lifespan.py`, `routes.py` | 120 |
| 10 | SSE keep-alive | `sse_keepalive.py`, modify `sse.py` | 120 |
| 11 | Worker hooks | modify `worker.py`, `stream.py` | 70 |
| 12 | Worker process | `worker_process.py` | 60 |
| 13 | Test infra | `conftest.py`, `test_checkpoint.py` | 70 |
| 14 | Integration test | `test_integration.py` | 80 |
| **Total** | | **20 files** | **~1,740** |
