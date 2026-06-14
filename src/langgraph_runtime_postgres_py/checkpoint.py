"""Bridge to langgraph-checkpoint-postgres AsyncPostgresSaver."""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from langgraph_runtime_postgres_py.database import _get_pool

_checkpointer: AsyncPostgresSaver | None = None


def Checkpointer(*args: Any, unpack_hook: Any = None, **kwargs: Any) -> AsyncPostgresSaver:
    """Return the singleton AsyncPostgresSaver instance."""
    global _checkpointer
    if _checkpointer is None:
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
    # setup() runs CREATE INDEX CONCURRENTLY which requires autocommit.
    # Run setup in a separate autocommit connection, then create the
    # checkpointer with the pool for normal operations.
    async with pool.connection() as conn:
        await conn.set_autocommit(True)
        saver = AsyncPostgresSaver(conn=conn)
        await saver.setup()
    _checkpointer = AsyncPostgresSaver(conn=pool)


async def exit_checkpointer() -> None:
    """Release checkpointer resources."""
    global _checkpointer
    _checkpointer = None


__all__ = ["Checkpointer", "start_checkpointer", "exit_checkpointer"]
