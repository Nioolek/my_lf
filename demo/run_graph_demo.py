"""Standalone LangGraph demo — run a real graph with Postgres checkpointer + Redis queue.

No API server needed. This directly exercises the core runtime modules.

Prerequisites:
    docker run -d --name lg-pg --restart unless-stopped \
        -e POSTGRES_USER=langgraph -e POSTGRES_PASSWORD=langgraph -e POSTGRES_DB=langgraph \
        -v lg_pg_data:/var/lib/postgresql/data -p 5433:5432 postgres:16-alpine
    docker run -d --name lg-redis --restart unless-stopped \
        -v lg_redis_data:/data -p 6380:6379 redis:7-alpine redis-server --appendonly yes

Usage:
    python run_graph_demo.py
"""

import asyncio
import json
import os
import sys
import selectors
from dotenv import load_dotenv

# ── 1. Load environment from .env ──────────────────────────────────────────

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# ── 2. Add local src to path ────────────────────────────────────────────────

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# ── 3. Event loop fix for Windows ──────────────────────────────────────────

def loop_factory():
    return asyncio.SelectorEventLoop(selectors.SelectSelector())


# ═══════════════════════════════════════════════════════════════════════════
# Demo 1: Simple Counter Graph
# ═══════════════════════════════════════════════════════════════════════════

async def demo_counter_graph():
    """A simple two-node graph: increment -> double, with Postgres checkpointing."""
    import structlog
    log = structlog.stdlib.get_logger("demo.counter")

    from typing import Annotated, TypedDict
    import operator
    from langgraph.graph import StateGraph, END

    from langgraph_runtime_postgres_py.database import start_pool, connect, stop_pool
    from langgraph_runtime_postgres_py.checkpoint import start_checkpointer, exit_checkpointer, Checkpointer
    from langgraph_runtime_postgres_py.ops import Threads

    class CounterState(TypedDict):
        count: Annotated[int, operator.add]
        messages: Annotated[list[str], operator.add]

    def increment(state: CounterState) -> CounterState:
        log.info("  [node] increment", count=state["count"])
        return {"count": 1, "messages": ["+1"]}

    def double(state: CounterState) -> CounterState:
        new_val = state["count"]
        log.info("  [node] double", count=state["count"], doubled=new_val * 2)
        return {"count": new_val, "messages": [f"x2={new_val*2}"]}

    def route(state: CounterState) -> str:
        if state["count"] >= 10:
            return "done"
        return "loop"

    builder = StateGraph(CounterState)
    builder.add_node("increment", increment)
    builder.add_node("double", double)
    builder.set_entry_point("increment")
    builder.add_conditional_edges("increment", route, {"loop": "double", "done": END})
    builder.add_edge("double", "increment")

    # Start runtime
    await start_pool()
    await start_checkpointer()

    checkpointer = Checkpointer()
    graph = builder.compile(checkpointer=checkpointer)

    # Create a thread for stateful execution
    async with connect() as conn:
        thread = await Threads.create(conn, metadata={"demo": "counter"})
        thread_id = str(thread["thread_id"])

    config = {"configurable": {"thread_id": thread_id}}

    # ── Run 1 ──
    log.info("=== Run 1: Starting from count=0 ===")
    result = await graph.ainvoke({"count": 0, "messages": ["start"]}, config)
    log.info("Result", count=result["count"], messages=result["messages"])

    # ── Run 2 (same thread, state accumulates) ──
    log.info("=== Run 2: Continuing on same thread ===")
    result2 = await graph.ainvoke({"count": 0, "messages": ["second run"]}, config)
    log.info("Result", count=result2["count"], messages=result2["messages"])

    # ── Check state history ──
    log.info("=== State History ===")
    i = 0
    async for snapshot in graph.aget_state_history(config):
        log.info(f"  checkpoint {i}", count=snapshot.values.get("count", 0), next=snapshot.next)
        i += 1

    # Cleanup
    async with connect() as conn:
        await Threads.delete(conn, thread_id=thread_id)
    await exit_checkpointer()
    await stop_pool()


# ═══════════════════════════════════════════════════════════════════════════
# Demo 2: Chat Agent with Human-in-the-Loop
# ═══════════════════════════════════════════════════════════════════════════

async def demo_hitl_graph():
    """A graph that pauses for human approval before proceeding."""
    import structlog
    log = structlog.stdlib.get_logger("demo.hitl")

    from typing import TypedDict
    from langgraph.graph import StateGraph, END

    from langgraph_runtime_postgres_py.database import start_pool, connect, stop_pool
    from langgraph_runtime_postgres_py.checkpoint import start_checkpointer, exit_checkpointer, Checkpointer
    from langgraph_runtime_postgres_py.ops import Threads

    class ApprovalState(TypedDict):
        request: str
        approved: bool
        result: str

    def review(state: ApprovalState) -> ApprovalState:
        log.info("  [node] review", request=state["request"])
        return {}  # Just pass through, waiting for human input

    def execute(state: ApprovalState) -> ApprovalState:
        log.info("  [node] execute", request=state["request"], approved=state.get("approved"))
        if state.get("approved"):
            return {"result": f"EXECUTED: {state['request']}"}
        return {"result": f"REJECTED: {state['request']}"}

    builder = StateGraph(ApprovalState)
    builder.add_node("review", review)
    builder.add_node("execute", execute)
    builder.set_entry_point("review")
    builder.add_edge("review", "execute")
    builder.add_edge("execute", END)

    await start_pool()
    await start_checkpointer()

    checkpointer = Checkpointer()
    graph = builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["execute"],  # Pause before execution
    )

    async with connect() as conn:
        thread = await Threads.create(conn, metadata={"demo": "hitl"})
        thread_id = str(thread["thread_id"])

    config = {"configurable": {"thread_id": thread_id}}

    # ── Step 1: Submit request (will pause before "execute") ──
    log.info("=== Step 1: Submit request (will interrupt) ===")
    result1 = await graph.ainvoke(
        {"request": "Delete production database", "approved": False, "result": ""},
        config,
    )
    log.info("Interrupted state", state=result1)

    # Check where we are
    state = await graph.aget_state(config)
    log.info("Waiting at node", next=state.next, request=state.values["request"])

    # ── Step 2: Human provides approval and resumes ──
    log.info("=== Step 2: Human approves and resumes ===")
    await graph.aupdate_state(config, {"approved": True}, as_node="review")
    result2 = await graph.ainvoke(None, config)
    log.info("Final result", result=result2["result"])

    # Cleanup
    async with connect() as conn:
        await Threads.delete(conn, thread_id=thread_id)
    await exit_checkpointer()
    await stop_pool()


# ═══════════════════════════════════════════════════════════════════════════
# Demo 3: Full API-style flow (Assistant + Thread + Run + Events)
# ═══════════════════════════════════════════════════════════════════════════

async def demo_full_api_flow():
    """Simulate the full API request lifecycle."""
    import structlog
    log = structlog.stdlib.get_logger("demo.api_flow")

    from typing import Annotated, TypedDict
    import operator
    from langgraph.graph import StateGraph, END

    from langgraph_runtime_postgres_py.database import start_pool, connect, stop_pool
    from langgraph_runtime_postgres_py.checkpoint import start_checkpointer, exit_checkpointer, Checkpointer
    from langgraph_runtime_postgres_py.run_queue import start_redis, stop_redis, enqueue_run, get_redis
    from langgraph_runtime_postgres_py.events import EventType, publish_event
    from langgraph_runtime_postgres_py.store import collect_store_from_env, get_store, exit_store
    from langgraph_runtime_postgres_py.ops import Assistants, Threads, Runs, Crons, RunEvents
    from langgraph_runtime_postgres_py.metrics import get_metrics

    class AgentState(TypedDict):
        query: str
        steps: Annotated[list[str], operator.add]
        answer: str

    def think(state: AgentState) -> AgentState:
        log.info("  [node] think", query=state["query"])
        return {"steps": [f"Thinking about: {state['query']}"]}

    def respond(state: AgentState) -> AgentState:
        log.info("  [node] respond", steps=state["steps"])
        return {"answer": f"Answer to '{state['query']}': 42"}

    builder = StateGraph(AgentState)
    builder.add_node("think", think)
    builder.add_node("respond", respond)
    builder.set_entry_point("think")
    builder.add_edge("think", "respond")
    builder.add_edge("respond", END)

    # Start all services
    await start_pool()
    await start_checkpointer()
    await start_redis()
    await collect_store_from_env()

    checkpointer = Checkpointer()
    graph = builder.compile(checkpointer=checkpointer)

    async with connect() as conn:
        # 1. Create assistant (this is what API does when a graph is registered)
        assistant = await Assistants.create(
            conn, graph_id="agent", name="Demo Agent",
            metadata={"type": "qa"}, config={},
        )
        assistant_id = assistant["assistant_id"]
        log.info("Created assistant", id=str(assistant_id))

        # 2. Create thread
        thread = await Threads.create(conn, metadata={"user": "demo_user"})
        thread_id = thread["thread_id"]
        log.info("Created thread", id=str(thread_id))

        # 3. Create run (pending)
        run = await Runs.create(
            conn, thread_id=thread_id, assistant_id=assistant_id,
            kwargs={"input": {"query": "What is the meaning of life?"}},
            metadata={"attempt": 1},
        )
        run_id = run["run_id"]
        log.info("Created run", id=str(run_id), status=run["status"])

        # 4. Publish event
        await publish_event(EventType.RUN_STARTED, {
            "run_id": str(run_id), "thread_id": str(thread_id),
        })
        log.info("Published RUN_STARTED event")

        # 5. Enqueue run to Redis (worker would pick this up)
        msg_id = await enqueue_run({
            "run_id": str(run_id), "thread_id": str(thread_id),
            "assistant_id": str(assistant_id), "attempt": 1,
        })
        log.info("Enqueued run to Redis", msg_id=str(msg_id))

        # 6. Actually execute the graph (in real system, worker does this)
        await Runs.update(conn, run_id=run_id, status="running")
        config = {"configurable": {"thread_id": str(thread_id)}}
        result = await graph.ainvoke(
            {"query": "What is the meaning of life?", "steps": [], "answer": ""},
            config,
        )
        log.info("Graph executed", answer=result["answer"], steps=result["steps"])

        # 7. Mark run completed
        await Runs.update(conn, run_id=run_id, status="success")
        await publish_event(EventType.RUN_COMPLETED, {
            "run_id": str(run_id), "thread_id": str(thread_id),
        })
        log.info("Published RUN_COMPLETED event")

        # 8. Check metrics
        metrics = get_metrics()
        log.info("Metrics", workers=metrics["workers"], pool=metrics["pool"])

        # 9. Search threads
        threads = await Threads.search(conn, metadata={"user": "demo_user"})
        log.info("Found threads", count=len(threads))

        # 10. Cleanup
        await Runs.delete(conn, run_id=run_id)
        await Threads.delete(conn, thread_id=thread_id)
        await Assistants.delete(conn, assistant_id=assistant_id)
        log.info("Cleaned up all entities")

    await exit_store()
    await exit_checkpointer()
    await stop_redis()
    await stop_pool()


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

async def main():
    print()
    print("=" * 70)
    print("  LangGraph + Postgres Runtime Demo")
    print("=" * 70)
    print()

    print(">>> Demo 1: Counter Graph (increment -> double loop)")
    print("-" * 70)
    await demo_counter_graph()

    print()
    print(">>> Demo 2: Human-in-the-Loop (interrupt before execution)")
    print("-" * 70)
    await demo_hitl_graph()

    print()
    print(">>> Demo 3: Full API-style Flow (Assistant -> Thread -> Run -> Events)")
    print("-" * 70)
    await demo_full_api_flow()

    print()
    print("=" * 70)
    print("  All demos completed successfully!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=loop_factory)