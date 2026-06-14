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
                "DATABASE_URI is required for langgraph_runtime_postgres_py. "
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