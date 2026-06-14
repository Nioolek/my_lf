"""Internal management routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langgraph_api.route import ApiRoute


async def _truncate(request):
    from langgraph_runtime_postgres_py.database import _get_pool
    pool = await _get_pool()
    async with pool.connection() as conn:
        for table in ["run_events", "runs", "crons", "threads", "assistant_versions", "assistants", "worker_registry"]:
            await conn.execute(f"DELETE FROM {table}")
    return {"ok": True}


async def _debug_thread(request):
    thread_id = request.path_params["thread_id"]
    from langgraph_runtime_postgres_py.database import _get_pool
    pool = await _get_pool()
    async with pool.connection() as conn:
        rows = await conn.execute("SELECT * FROM threads WHERE thread_id = %s", (thread_id,))
        thread = dict(rows[0]) if rows else None
        rows = await conn.execute("SELECT * FROM runs WHERE thread_id = %s ORDER BY created_at DESC", (thread_id,))
        runs = [dict(r) for r in rows]
    return {"thread": thread, "runs": runs}


def _get_routes() -> list:
    """Lazily build routes to avoid heavy import at module load time."""
    from langgraph_api.route import ApiRoute
    return [
        ApiRoute("/internal/truncate", _truncate, methods=["POST"]),
        ApiRoute("/internal/debug/thread/{thread_id}", _debug_thread, methods=["GET"]),
    ]


ROUTES: list = []
"""Routes list — populated by _get_routes() at startup when langgraph_api is available."""
