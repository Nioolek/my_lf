# LangGraph Runtime Postgres — Design Spec

**Date**: 2026-06-14
**Status**: Approved
**Version**: 1.0

## 1. Purpose

Implement `langgraph_runtime_postgres`, a production-grade runtime backend for LangGraph API that replaces the in-memory runtime (`langgraph_runtime_inmem`) with Postgres for data persistence and Redis for distributed task queuing. This enables horizontal scaling, data durability, and multi-worker deployments.

## 2. Problem

The `langgraph-api` pip package only ships `langgraph_runtime_inmem`. All ops data (assistants, threads, runs, crons), checkpoint state, and store data live in memory with optional pickle-file persistence. This means:

- **No data durability** — process restart loses all state
- **No horizontal scaling** — single-process asyncio.Queue cannot span workers
- **No production-grade persistence** — pickle files are not suitable for concurrent access
- **SSE connections drop on interrupt** — HITL (human-in-the-loop) requires reconnection
- **No process event notifications** — webhooks only fire on run completion

## 3. Architecture

### 3.1 Runtime Dispatch

`langgraph_runtime/__init__.py` uses `LANGGRAPH_RUNTIME_EDITION` env var + `sys.modules` remapping:

```
LANGGRAPH_RUNTIME_EDITION=postgres
  → imports langgraph_runtime_postgres
  → remaps langgraph_runtime.checkpoint → langgraph_runtime_postgres.checkpoint
  → remaps langgraph_runtime.database   → langgraph_runtime_postgres.database
  → ... (ops, queue, store, lifespan, metrics, retry, routes)
```

### 3.2 Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    langgraph_api (v0.10.0)                   │
│  server.py │ api/ │ auth/ │ sse.py* │ worker.py* │ stream.py*│
└──────────────────────┬──────────────────────────────────────┘
                       │ imports
┌──────────────────────▼──────────────────────────────────────┐
│                  langgraph_runtime                           │
│         (dynamic dispatcher, no changes needed)              │
└──────────────────────┬──────────────────────────────────────┘
                       │ LANGGRAPH_RUNTIME_EDITION=postgres
┌──────────────────────▼──────────────────────────────────────┐
│              langgraph_runtime_postgres (NEW)                │
│                                                              │
│  ┌──────────┐ ┌──────────┐ ┌───────────┐ ┌──────────────┐  │
│  │ database │ │   ops    │ │checkpoint │ │    store     │  │
│  │ (pgpool) │ │(CRUD SQL)│ │ (bridge)  │ │(KV+pgvector) │  │
│  └────┬─────┘ └────┬─────┘ └─────┬─────┘ └──────┬───────┘  │
│       │             │             │               │          │
│  ┌────▼─────┐ ┌─────▼──────┐ ┌───▼────────┐ ┌───▼────────┐ │
│  │  queue   │ │  events    │ │  lifespan  │ │  metrics   │ │
│  │(Redis X) │ │(Redis Pub) │ │(lifecycle) │ │(prometheus)│ │
│  └──────────┘ └────────────┘ └────────────┘ └────────────┘ │
│                                                              │
│  ┌──────────────┐ ┌──────────────┐                          │
│  │worker_process│ │sse_keepalive │                          │
│  │(standalone)  │ │  (patch)     │                          │
│  └──────────────┘ └──────────────┘                          │
└──────────────────────────────────────────────────────────────┘
         │                    │
    ┌────▼────┐          ┌───▼────┐
    │Postgres │          │ Redis  │
    │  (data) │          │(queue) │
    └─────────┘          └────────┘
```

### 3.3 Module Responsibilities

| Module | Responsibility | Lines (est.) |
|--------|---------------|-------------|
| `__init__.py` | Package version + module exposure | 20 |
| `database.py` | psycopg3 async connection pool, migration runner, healthcheck | 150 |
| `ops.py` | PG SQL CRUD for Assistants, Threads, Runs, Crons | 2000 |
| `checkpoint.py` | Thin bridge to `langgraph-checkpoint-postgres` AsyncPostgresSaver | 30 |
| `store.py` | PG KV store + pgvector vector search | 300 |
| `queue.py` | Redis Streams consumer group distributed queue | 400 |
| `events.py` | Redis Pub/Sub event bus | 150 |
| `lifespan.py` | Application startup/shutdown orchestration | 200 |
| `metrics.py` | Worker + DB metrics | 50 |
| `retry.py` | psycopg3 retry decorator | 30 |
| `routes.py` | Internal management HTTP routes | 100 |
| `sse_keepalive.py` | SSE interrupt keep-alive patch | 100 |
| `worker_process.py` | Standalone worker process entry point | 80 |
| `migrations/*.sql` | SQL migration files | 120 |

### 3.4 Modified Files (langgraph_api)

| File | Change | Lines |
|------|--------|-------|
| `sse.py` | Interrupt event handling + keep-alive | +50 |
| `worker.py` | Event emission hooks | +30 |
| `stream.py` | Interrupt detection in astream_state | +40 |

## 4. Data Model

### 4.1 Ops Tables

```sql
-- assistants: graph configurations with version history
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

CREATE TABLE assistant_versions (
    assistant_id UUID NOT NULL REFERENCES assistants(assistant_id),
    version INTEGER NOT NULL,
    graph_id TEXT NOT NULL,
    config JSONB NOT NULL DEFAULT '{}',
    context JSONB NOT NULL DEFAULT '{}',
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    name TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (assistant_id, version)
);

-- threads: conversation/workflow sessions
CREATE TABLE threads (
    thread_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    metadata JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'idle',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_threads_status ON threads(status);

-- runs: execution records
CREATE TABLE runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id UUID NOT NULL REFERENCES threads(thread_id),
    assistant_id UUID NOT NULL REFERENCES assistants(assistant_id),
    status TEXT NOT NULL DEFAULT 'pending',
    kwargs JSONB NOT NULL DEFAULT '{}',
    result JSONB,
    multitask_strategy TEXT NOT NULL DEFAULT 'reject',
    metadata JSONB NOT NULL DEFAULT '{}',
    attempt INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_runs_thread_id ON runs(thread_id);
CREATE INDEX idx_runs_status ON runs(status);

-- run_events: structured event log per run
CREATE TABLE run_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES runs(run_id),
    span_id UUID NOT NULL,
    event TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    tags JSONB NOT NULL DEFAULT '[]',
    data JSONB NOT NULL DEFAULT '{}',
    metadata JSONB NOT NULL DEFAULT '{}',
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- crons: scheduled job definitions
CREATE TABLE crons (
    cron_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assistant_id UUID NOT NULL REFERENCES assistants(assistant_id),
    thread_id UUID REFERENCES threads(thread_id),
    name TEXT NOT NULL DEFAULT '',
    schedule TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}',
    next_run_date TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- worker_registry: multi-worker heartbeat tracking
CREATE TABLE worker_registry (
    worker_id TEXT PRIMARY KEY,
    hostname TEXT NOT NULL,
    pid INTEGER NOT NULL,
    capacity INTEGER NOT NULL DEFAULT 1,
    active_jobs INTEGER NOT NULL DEFAULT 0,
    last_heartbeat TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status TEXT NOT NULL DEFAULT 'active'
);
```

### 4.2 Store Tables

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE store_kv (
    namespace TEXT NOT NULL,
    key TEXT NOT NULL,
    value JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    PRIMARY KEY (namespace, key)
);

CREATE TABLE store_vectors (
    namespace TEXT NOT NULL,
    key TEXT NOT NULL,
    path TEXT NOT NULL,
    embedding vector(1536),
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (namespace, key, path)
);
```

### 4.3 Checkpoint Tables (REUSED)

Already provided by `langgraph-checkpoint-postgres`:
- `checkpoints` — checkpoint metadata + inline primitive channel values
- `checkpoint_blobs` — serialized complex channel values (blob separation)
- `checkpoint_writes` — pending/intermediate writes per checkpoint

**No new tables needed for checkpoints.**

### 4.4 Redis Keys

| Key | Type | Purpose |
|-----|------|---------|
| `lg:runs` | Stream | Task queue (XADD by API, XREADGROUP by workers) |
| `lg:events` | Pub/Sub channel | Event bus (publish by workers, subscribe by SSE) |

## 5. Key Interfaces

### 5.1 Ops Classes (must match inmem signatures)

```python
class Assistants:
    @staticmethod
    async def create(conn, *, graph_id, config, context, metadata, name, description) -> Assistant
    @staticmethod
    async def get(conn, *, assistant_id, select_fields=None) -> Assistant
    @staticmethod
    async def update(conn, *, assistant_id, ...) -> Assistant
    @staticmethod
    async def search(conn, *, graph_id=None, metadata=None, limit=10, offset=0) -> list[Assistant]
    @staticmethod
    async def delete(conn, *, assistant_id) -> None
    @staticmethod
    async def versions(conn, *, assistant_id, limit=10, offset=0) -> list[AssistantVersion]

class Threads:
    @staticmethod
    async def create(conn, *, thread_id=None, metadata=None, if_not_exists=None) -> Thread
    @staticmethod
    async def get(conn, *, thread_id) -> Thread
    @staticmethod
    async def update(conn, *, thread_id, metadata=None, status=None) -> Thread
    @staticmethod
    async def search(conn, *, metadata=None, values=None, status=None, limit=10, offset=0) -> list[Thread]
    @staticmethod
    async def delete(conn, *, thread_id) -> None
    @staticmethod
    async def get_state(conn, *, thread_id, checkpoint_ns="", subgraphs=False) -> StateSnapshot
    @staticmethod
    async def update_state(conn, *, thread_id, values, as_node=None, checkpoint_id=None) -> Config
    @staticmethod
    async def get_history(conn, *, thread_id, limit=10, before=None, ...) -> list[StateSnapshot]

class Runs:
    @staticmethod
    async def create(conn, *, thread_id, assistant_id, ...) -> Run
    @staticmethod
    async def get(conn, *, run_id) -> Run
    @staticmethod
    async def search(conn, *, thread_id=None, status=None, limit=10, offset=0) -> list[Run]
    @staticmethod
    async def delete(conn, *, run_id) -> None
    @staticmethod
    async def next(*, wait=True, limit=1) -> AsyncIterator[tuple[Run, int]]
    @staticmethod
    async def stats(conn) -> dict
    @staticmethod
    async def sweep() -> None
```

### 5.2 Checkpointer Bridge

```python
_checkpointer: AsyncPostgresSaver | None = None

def Checkpointer(*args, **kwargs) -> AsyncPostgresSaver:
    # Returns singleton, created on first call
    ...

async def start_checkpointer():
    # Runs BasePostgresSaver.setup() to create/migrate checkpoint tables
    ...

async def exit_checkpointer():
    # Closes checkpointer connections
    ...
```

### 5.3 Queue Interface

```python
async def queue():
    """Main consumption loop using Redis Streams XREADGROUP"""
    ...

async def enqueue_run(run: dict) -> str:
    """XADD a run to the Redis Stream"""
    ...
```

### 5.4 Events Interface

```python
class EventType(str, Enum):
    RUN_CREATED = "run.created"
    RUN_STARTED = "run.started"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_INTERRUPTED = "run.interrupted"
    RUN_RESUMED = "run.resumed"
    NODE_STARTED = "node.started"
    NODE_COMPLETED = "node.completed"

async def publish_event(event_type: EventType, payload: dict) -> None
async def subscribe_events(event_types=None, thread_id=None) -> AsyncIterator[dict]
```

## 6. Redis Streams Queue Design

### 6.1 Message Flow

```
API creates run → Runs.create(conn, ...) → enqueue_run(run)
                                              │
                                     XADD lg:runs {run_id, thread_id, ...}
                                              │
                         ┌────────────────────┼────────────────────┐
                         ▼                    ▼                    ▼
                    Worker 1            Worker 2            Worker N
                    XREADGROUP          XREADGROUP          XREADGROUP
                         │                    │                    │
                    worker.worker()     worker.worker()     worker.worker()
                         │                    │                    │
                    XACK + XDEL         XACK + XDEL         XACK + XDEL
                         │                    │                    │
                    publish_event       publish_event       publish_event
                    call_webhook        call_webhook        call_webhook
```

### 6.2 Consumer Group

- Group name: `workers`
- Consumer name: `{hostname}:{pid}-{uuid8}`
- Block timeout: 5000ms
- Pending recovery: `XAUTOCLAIM` after 60s for stale consumers

### 6.3 Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Stream vs List | Streams + Consumer Groups | Message ack, replay, consumer failover |
| Message format | `dict[str, str]` | Redis Streams native format |
| Ack strategy | XACK + XDEL after completion | Prevents pending pile-up |
| Dead worker detection | XAUTOCLAIM 60s timeout | Auto-reassign stale messages |

## 7. SSE Interrupt Keep-Alive

### 7.1 Current Behavior
- Stream ends → `more_body: False` → connection closes
- Interrupt events cause premature connection close
- Client must reconnect to poll for resume

### 7.2 Target Behavior
- Interrupt detected → send `interrupt` event → `more_body: True` (keep alive)
- Enter wait mode: Redis Pub/Sub or poll Run status
- Resume detected → send `resume` event → continue streaming
- Only close on: run completion, timeout, or client disconnect

### 7.3 Implementation

```python
# sse.py changes
INTERRUPT_EVENT = b"interrupt"
RESUME_EVENT = b"resume"

class EventSourceResponse:
    async def _wait_for_resume(self, send, interrupt_data, timeout=3600):
        """Wait for interrupt resolution, maintaining heartbeat"""
        ...

# stream.py changes
async def astream_state(graph, run, ...):
    async for event in graph.astream(...):
        if _is_interrupt_event(event):
            yield (INTERRUPT_EVENT, {...})
            await wait_for_resume(thread_id, run_id)
            yield (RESUME_EVENT, {...})
            continue
        yield event
```

## 8. Configuration

### 8.1 Environment Variables (already in langgraph_api/config)

```bash
# Postgres
DATABASE_URI=postgresql://user:pass@localhost:5432/langgraph
POSTGRES_URI=postgresql://user:pass@localhost:5432/langgraph  # fallback
LANGGRAPH_POSTGRES_POOL_MAX_SIZE=150

# Redis (already defined in config/__init__.py)
REDIS_URI=redis://localhost:6379
REDIS_URI_CUSTOM=redis://localhost:6379
REDIS_CLUSTER=false
REDIS_MAX_CONNECTIONS=2000
REDIS_KEY_PREFIX=""

# Runtime selection
LANGGRAPH_RUNTIME_EDITION=postgres
```

### 8.2 Dependencies

```toml
[project]
name = "langgraph-runtime-postgres"
version = "0.1.0"
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

## 9. Testing Strategy

### 9.1 Checkpointer Validation

Use `langgraph-checkpoint-conformance` to validate our bridged checkpointer:

```python
from langgraph.checkpoint.conformance import checkpointer_test, validate

@checkpointer_test(name="PostgresRuntimeSaver")
async def pg_runtime_checkpointer():
    from langgraph_runtime_postgres.checkpoint import Checkpointer
    yield Checkpointer()

async def test_conformance():
    report = await validate(pg_runtime_checkpointer)
    assert report.passed_all_base()
```

### 9.2 Ops Tests

Test against real Postgres via testcontainers:
- CRUD round-trips for each entity type
- Search/filter/pagination
- Concurrent access
- Migration idempotency

### 9.3 Queue Tests

Test against real Redis via testcontainers:
- Enqueue → consume → ack cycle
- Multi-consumer load distribution
- Stale consumer recovery (XAUTOCLAIM)
- Graceful shutdown

### 9.4 Integration Tests

End-to-end: create thread → create run → stream events → interrupt → resume → verify checkpoint

## 10. Non-Goals (Out of Scope)

- Postgres-based queue (Redis is required for distributed workers)
- MySQL/SQLite runtime backends (the architecture supports them, but not in this spec)
- LangGraph Cloud parity (this is about filling the open-source gap, not matching the SaaS)
- Migration UI/tooling beyond a basic CLI script
- Horizontal pod autoscaling (K8s-level concerns are deployment-specific)

## 11. Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| `ops.py` is large (~2000 lines) | Follow inmem ops structure closely; use parameterized SQL; test each class independently |
| Redis Streams complexity | Start with simple XREADGROUP loop; add XAUTOCLAIM later |
| SSE keep-alive may conflict with existing sse.py | Make changes minimal and behind feature flag (`LANGGRAPH_RUNTIME_EDITION=postgres`) |
| pgvector extension requirement | Make vector store optional; graceful degradation if pgvector not installed |
| Connection pool exhaustion | Use configurable pool sizes; add connection timeout metrics |
