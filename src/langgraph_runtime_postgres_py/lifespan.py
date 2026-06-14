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
    from langgraph_runtime_postgres_py.database import start_pool, stop_pool
    from langgraph_runtime_postgres_py.checkpoint import start_checkpointer, exit_checkpointer
    from langgraph_runtime_postgres_py.store import collect_store_from_env, get_store, exit_store
    from langgraph_runtime_postgres_py.run_queue import start_redis, stop_redis, queue
    from langgraph_runtime_postgres_py.sse_keepalive import apply_sse_patch
    from langgraph_api import config as api_config
    from langgraph_api import graph
    from langgraph_runtime_inmem.inmem_stream import start_stream, stop_stream
    from langgraph_api.asyncio import SimpleTaskGroup
    from langgraph_api.http import start_http_client, stop_http_client
    from langchain_core.runnables.config import var_child_runnable_config
    from langgraph_api.graph import collect_graphs_from_env
    from langgraph_api.cron_scheduler import cron_scheduler

    # --- SSE Patch ---
    apply_sse_patch()

    # --- Populate routes ---
    from langgraph_runtime_postgres_py.routes import _get_routes, ROUTES
    ROUTES.extend(_get_routes())

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
        from langgraph._internal._constants import CONFIG_KEY_RUNTIME
        langgraph_config = {"configurable": {CONFIG_KEY_RUNTIME: Runtime(store=store_instance)}}
    else:
        from langgraph.constants import CONFIG_KEY_STORE
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
