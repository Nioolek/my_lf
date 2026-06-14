"""End-to-end integration test: create thread → run → check state."""

import pytest


@pytest.mark.asyncio
async def test_create_thread_and_run(pg_uri, redis_uri):
    from langgraph_runtime_postgres_py.database import start_pool, connect
    from langgraph_runtime_postgres_py.ops import Threads, Runs

    await start_pool()

    async with connect() as conn:
        # Create thread
        thread = await Threads.create(conn, metadata={"user": "test"})
        assert thread["thread_id"] is not None
        assert thread["status"] == "idle"
        assert thread["metadata"]["user"] == "test"

        # Create assistant first
        from langgraph_runtime_postgres_py.ops import Assistants
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

    from langgraph_runtime_postgres_py.database import stop_pool
    await stop_pool()


@pytest.mark.asyncio
async def test_assistant_versioning(pg_uri, redis_uri):
    from langgraph_runtime_postgres_py.database import start_pool, connect
    from langgraph_runtime_postgres_py.ops import Assistants

    await start_pool()

    async with connect() as conn:
        a = await Assistants.create(conn, graph_id="test", config={"v": 1}, name="Test")
        await Assistants.update(conn, assistant_id=a["assistant_id"], config={"v": 2})
        versions = await Assistants.versions(conn, assistant_id=a["assistant_id"])
        assert len(versions) >= 1

    from langgraph_runtime_postgres_py.database import stop_pool
    await stop_pool()


@pytest.mark.asyncio
async def test_cron_lifecycle(pg_uri, redis_uri):
    from langgraph_runtime_postgres_py.database import start_pool, connect
    from langgraph_runtime_postgres_py.ops import Assistants, Crons

    await start_pool()

    async with connect() as conn:
        a = await Assistants.create(conn, graph_id="cron_graph", name="CronTest")
        cron = await Crons.create(
            conn,
            assistant_id=a["assistant_id"],
            schedule="0 * * * *",  # Every hour
            payload={"input": "tick"},
            name="Hourly Cron",
        )
        assert cron["cron_id"] is not None
        assert cron["schedule"] == "0 * * * *"

        # Search
        crons = await Crons.search(conn, assistant_id=a["assistant_id"])
        assert len(crons) >= 1

        # Delete
        await Crons.delete(conn, cron_id=cron["cron_id"])
        with pytest.raises(Exception):
            await Crons.get(conn, cron_id=cron["cron_id"])

    from langgraph_runtime_postgres_py.database import stop_pool
    await stop_pool()


@pytest.mark.asyncio
async def test_worker_registry(pg_uri, redis_uri):
    from langgraph_runtime_postgres_py.database import start_pool, connect

    await start_pool()

    async with connect() as conn:
        # The worker_registry table should exist
        await conn.execute("SELECT COUNT(*) FROM worker_registry")

    from langgraph_runtime_postgres_py.database import stop_pool
    await stop_pool()
