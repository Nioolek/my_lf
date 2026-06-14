"""Full integration test with real PostgreSQL and Redis.

Prerequisites:
    docker run -d --name langgraph-test-postgres \
        -e POSTGRES_USER=langgraph -e POSTGRES_PASSWORD=langgraph \
        -e POSTGRES_DB=langgraph -p 5433:5432 postgres:16-alpine
    docker run -d --name langgraph-test-redis -p 6380:6379 redis:7-alpine

Run:
    pytest src/langgraph_runtime_postgres_py/tests/test_full_integration.py -v -s
"""

import asyncio
import os
import sys
from typing import TypedDict
from uuid import uuid4

# Ensure src path is first
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../.."))

# Set environment before importing langgraph_api
os.environ["LANGGRAPH_RUNTIME_EDITION"] = "postgres"
os.environ["DATABASE_URI"] = "postgresql://langgraph:langgraph@localhost:5433/langgraph"
os.environ["REDIS_URI"] = "redis://localhost:6380"
os.environ["N_JOBS_PER_WORKER"] = "2"
os.environ["LANGGRAPH_AES_KEY"] = "1234567890123456"  # Exactly 16 bytes


class State(TypedDict):
    count: int
    messages: list[str]


async def test_full_integration():
    """Full integration test with real LangGraph graph."""
    import structlog
    structlog.stdlib.get_logger(__name__).info("=== Starting Full Integration Test ===")

    # 1. Initialize database and checkpointer
    from langgraph_runtime_postgres_py.database import start_pool, connect, stop_pool
    from langgraph_runtime_postgres_py.checkpoint import start_checkpointer, exit_checkpointer
    from langgraph_runtime_postgres_py.run_queue import start_redis, stop_redis
    from langgraph_runtime_postgres_py.store import collect_store_from_env, get_store, exit_store
    from langgraph_runtime_postgres_py.events import EventType, publish_event

    structlog.stdlib.get_logger(__name__).info("Step 1: Starting pool and checkpointer...")
    await start_pool()
    await start_checkpointer()
    await start_redis()
    await collect_store_from_env()
    store = await get_store()

    # 2. Test OPS CRUD
    from langgraph_runtime_postgres_py.ops import Assistants, Threads, Runs, Crons, RunEvents

    structlog.stdlib.get_logger(__name__).info("Step 2: Testing OPS CRUD...")

    async with connect() as conn:
        # Create assistant
        assistant = await Assistants.create(
            conn,
            graph_id="test_graph",
            config={"model": "gpt-4"},
            name="Test Assistant",
            metadata={"env": "test"},
        )
        assistant_id = assistant["assistant_id"]
        structlog.stdlib.get_logger(__name__).info("Created assistant", assistant_id=str(assistant_id))

        # Create thread
        thread = await Threads.create(
            conn,
            metadata={"user": "test_user", "session": "integration_test"},
        )
        thread_id = thread["thread_id"]
        structlog.stdlib.get_logger(__name__).info("Created thread", thread_id=str(thread_id))

        # Create run
        run = await Runs.create(
            conn,
            thread_id=thread_id,
            assistant_id=assistant_id,
            kwargs={"input": "Hello, world!"},
            metadata={"test": True},
        )
        run_id = run["run_id"]
        structlog.stdlib.get_logger(__name__).info("Created run", run_id=str(run_id), status=run["status"])

        # Search threads
        threads = await Threads.search(conn, metadata={"user": "test_user"})
        assert len(threads) >= 1
        structlog.stdlib.get_logger(__name__).info("Thread search found", count=len(threads))

        # Search runs
        runs = await Runs.search(conn, thread_id=thread_id)
        assert len(runs) >= 1
        structlog.stdlib.get_logger(__name__).info("Run search found", count=len(runs))

        # Update run status
        updated_run = await Runs.update(conn, run_id=run_id, status="running")
        assert updated_run["status"] == "running"
        structlog.stdlib.get_logger(__name__).info("Updated run status", status=updated_run["status"])

        # Create run event
        event = await RunEvents.create(
            conn,
            run_id=run_id,
            span_id=uuid4(),
            event="llm_start",
            name="LLM Call",
            tags=["llm", "gpt-4"],
            data={"prompt": "Hello"},
        )
        structlog.stdlib.get_logger(__name__).info("Created run event", event_id=str(event["event_id"]))

        # Create cron
        cron = await Crons.create(
            conn,
            assistant_id=assistant_id,
            schedule="0 * * * *",
            payload={"trigger": "hourly"},
            name="Hourly Cron",
        )
        structlog.stdlib.get_logger(__name__).info("Created cron", cron_id=str(cron["cron_id"]))

        # Test assistant versioning
        await Assistants.update(conn, assistant_id=assistant_id, config={"model": "gpt-4o"})
        versions = await Assistants.versions(conn, assistant_id=assistant_id)
        assert len(versions) >= 1
        structlog.stdlib.get_logger(__name__).info("Assistant versions", count=len(versions))

    # 3. Test Checkpointer with LangGraph
    structlog.stdlib.get_logger(__name__).info("Step 3: Testing Checkpointer with LangGraph graph...")

    from langgraph.graph import StateGraph, END
    from langgraph_runtime_postgres_py.checkpoint import Checkpointer

    checkpointer = Checkpointer()

    def increment(state: State) -> State:
        return {"count": state["count"] + 1, "messages": state["messages"] + ["incremented"]}

    def double(state: State) -> State:
        return {"count": state["count"] * 2, "messages": state["messages"] + ["doubled"]}

    # Build graph
    graph_builder = StateGraph(State)
    graph_builder.add_node("increment", increment)
    graph_builder.add_node("double", double)
    graph_builder.set_entry_point("increment")
    graph_builder.add_edge("increment", "double")
    graph_builder.add_edge("double", END)

    compiled_graph = graph_builder.compile(checkpointer=checkpointer)

    # Run graph
    config = {"configurable": {"thread_id": str(thread_id)}}
    initial_state = {"count": 5, "messages": ["start"]}

    result = await compiled_graph.ainvoke(initial_state, config)
    structlog.stdlib.get_logger(__name__).info("Graph result", result=result)
    assert result["count"] == 12  # (5 + 1) * 2 = 12
    assert len(result["messages"]) == 3

    # Get state
    state_snapshot = await compiled_graph.aget_state(config)
    structlog.stdlib.get_logger(__name__).info("State snapshot", values=state_snapshot.values)
    assert state_snapshot.values["count"] == 12

    # Get history
    history = []
    async for snapshot in compiled_graph.aget_state_history(config):
        history.append(snapshot)
    structlog.stdlib.get_logger(__name__).info("State history", count=len(history))
    assert len(history) >= 1

    # 4. Test Store
    structlog.stdlib.get_logger(__name__).info("Step 4: Testing Store...")

    from langgraph.store.base import PutOp, GetOp, SearchOp, Item

    # Put
    ops = [
        PutOp(namespace=("test", "ns"), key="key1", value={"data": "value1"}),
        PutOp(namespace=("test", "ns"), key="key2", value={"data": "value2"}, ttl=3600),
    ]
    results = await store.abatch(ops)
    structlog.stdlib.get_logger(__name__).info("Store put operations", count=len(results))

    # Get
    get_ops = [GetOp(namespace=("test", "ns"), key="key1")]
    get_results = await store.abatch(get_ops)
    assert get_results[0] is not None
    assert isinstance(get_results[0], Item)
    assert get_results[0].value == {"data": "value1"}
    structlog.stdlib.get_logger(__name__).info("Store get result", value=get_results[0].value)

    # Search
    search_ops = [SearchOp(namespace_prefix=("test",), limit=10)]
    search_results = await store.abatch(search_ops)
    assert len(search_results[0]) >= 1
    structlog.stdlib.get_logger(__name__).info("Store search results", items=len(search_results[0]))

    # 5. Test Events
    structlog.stdlib.get_logger(__name__).info("Step 5: Testing Events...")

    await publish_event(EventType.RUN_STARTED, {
        "run_id": str(run_id),
        "thread_id": str(thread_id),
        "assistant_id": str(assistant_id),
    })
    structlog.stdlib.get_logger(__name__).info("Published RUN_STARTED event")

    await publish_event(EventType.THREAD_UPDATED, {
        "thread_id": str(thread_id),
        "status": "running",
    })
    structlog.stdlib.get_logger(__name__).info("Published THREAD_UPDATED event")

    # 6. Test Queue
    structlog.stdlib.get_logger(__name__).info("Step 6: Testing Queue...")

    from langgraph_runtime_postgres_py.run_queue import enqueue_run, get_redis

    redis = await get_redis()
    await redis.ping()
    structlog.stdlib.get_logger(__name__).info("Redis ping successful")

    msg_id = await enqueue_run({
        "run_id": str(run_id),
        "thread_id": str(thread_id),
        "assistant_id": str(assistant_id),
        "attempt": 1,
    })
    structlog.stdlib.get_logger(__name__).info("Enqueued run", msg_id=str(msg_id))

    # Check stream length
    stream_info = await redis.xinfo_stream("lg:runs")
    structlog.stdlib.get_logger(__name__).info("Stream info", length=stream_info.get("length", 0))

    # 7. Test Metrics
    structlog.stdlib.get_logger(__name__).info("Step 7: Testing Metrics...")

    from langgraph_runtime_postgres_py.metrics import get_metrics
    metrics = get_metrics()
    structlog.stdlib.get_logger(__name__).info("Metrics", metrics=metrics)
    assert "workers" in metrics
    assert "pool" in metrics

    # 8. Cleanup
    structlog.stdlib.get_logger(__name__).info("Step 8: Cleanup...")

    async with connect() as conn:
        await Crons.delete(conn, cron_id=cron["cron_id"])
        await Runs.delete(conn, run_id=run_id)
        await Threads.delete(conn, thread_id=thread_id)
        await Assistants.delete(conn, assistant_id=assistant_id)
        structlog.stdlib.get_logger(__name__).info("Deleted all test entities")

    await exit_store()
    await exit_checkpointer()
    await stop_redis()
    await stop_pool()

    structlog.stdlib.get_logger(__name__).info("=== Full Integration Test PASSED ===")


async def test_graph_with_interrupt():
    """Test graph with interrupt for HITL simulation."""
    import structlog
    structlog.stdlib.get_logger(__name__).info("=== Testing Graph with Interrupt ===")

    from langgraph_runtime_postgres_py.database import start_pool, connect, stop_pool
    from langgraph_runtime_postgres_py.checkpoint import start_checkpointer, exit_checkpointer

    await start_pool()
    await start_checkpointer()

    from langgraph.graph import StateGraph, END
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph_runtime_postgres_py.checkpoint import Checkpointer

    checkpointer = Checkpointer()

    class InterruptState(TypedDict):
        value: int
        approved: bool

    def check_approval(state: InterruptState) -> InterruptState:
        # In real graph, this would check for human approval
        return state

    def process(state: InterruptState) -> InterruptState:
        return {"value": state["value"] * 10, "approved": True}

    graph_builder = StateGraph(InterruptState)
    graph_builder.add_node("check", check_approval)
    graph_builder.add_node("process", process)
    graph_builder.set_entry_point("check")
    graph_builder.add_edge("check", "process")
    graph_builder.add_edge("process", END)

    compiled_graph = graph_builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["process"],  # Interrupt before processing
    )

    # Create test thread
    from langgraph_runtime_postgres_py.ops import Threads
    async with connect() as conn:
        thread = await Threads.create(conn, metadata={"test": "interrupt"})
        thread_id = thread["thread_id"]

    config = {"configurable": {"thread_id": str(thread_id)}}

    # First run - will interrupt before "process"
    result = await compiled_graph.ainvoke({"value": 5, "approved": False}, config)
    structlog.stdlib.get_logger(__name__).info("First run (interrupted)", result=result)

    # Check state at interrupt
    state = await compiled_graph.aget_state(config)
    structlog.stdlib.get_logger(__name__).info("State at interrupt", values=state.values, next=state.next)
    # Should be interrupted before "process"

    # Resume - provide approval and continue
    result2 = await compiled_graph.ainvoke(None, config)
    structlog.stdlib.get_logger(__name__).info("Second run (resumed)", result=result2)

    # Cleanup
    async with connect() as conn:
        await Threads.delete(conn, thread_id=thread_id)

    await exit_checkpointer()
    await stop_pool()

    structlog.stdlib.get_logger(__name__).info("=== Interrupt Test PASSED ===")


if __name__ == "__main__":
    # On Windows, psycopg3 async requires SelectorEventLoop
    import sys
    if sys.platform == "win32":
        import asyncio
        import selectors
        asyncio.run(test_full_integration(), loop_factory=asyncio.SelectorEventLoop(selectors.SelectSelector()))
        asyncio.run(test_graph_with_interrupt(), loop_factory=asyncio.SelectorEventLoop(selectors.SelectSelector()))
    else:
        asyncio.run(test_full_integration())
        asyncio.run(test_graph_with_interrupt())