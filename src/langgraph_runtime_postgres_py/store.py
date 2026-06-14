"""Postgres-backed key-value store with optional pgvector support."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from langgraph.store.base import (
    GetOp,
    Item,
    ListNamespacesOp,
    Op,
    PutOp,
    SearchItem,
    SearchOp,
)
from langgraph.store.base.batch import AsyncBatchedBaseStore

logger = structlog.stdlib.get_logger(__name__)

_STORE_CONFIG: dict[str, Any] | None = None
STORE: "PgStore | None" = None


def set_store_config(config: dict[str, Any] | None) -> None:
    global _STORE_CONFIG
    _STORE_CONFIG = config


def _ns_to_str(namespace: tuple[str, ...]) -> str:
    """Convert namespace tuple to string."""
    return "/".join(namespace)


class PgStore(AsyncBatchedBaseStore):
    """Postgres-backed key-value store."""

    def __init__(self) -> None:
        super().__init__()

    async def abatch(self, ops: Iterable[Op]) -> list[Any]:
        """Execute batch operations. Returns list of results matching Op types."""
        from langgraph_runtime_postgres_py.database import _get_pool
        from psycopg.rows import dict_row
        pool = await _get_pool()
        results: list[Any] = []

        async with pool.connection() as conn:
            for op in ops:
                if isinstance(op, PutOp):
                    ns_str = _ns_to_str(op.namespace)
                    key = op.key
                    value = op.value if op.value is not None else {}
                    expires_at = None
                    if op.ttl:
                        expires_at = datetime.now(UTC) + timedelta(seconds=op.ttl)
                    await conn.execute(
                        """INSERT INTO store_kv (namespace, key, value, expires_at)
                           VALUES (%s, %s, %s, %s)
                           ON CONFLICT (namespace, key) DO UPDATE
                           SET value = EXCLUDED.value, updated_at = NOW(), expires_at = EXCLUDED.expires_at""",
                        (ns_str, key, json.dumps(value), expires_at),
                    )
                    # PutOp returns None
                    results.append(None)

                elif isinstance(op, GetOp):
                    ns_str = _ns_to_str(op.namespace)
                    key = op.key
                    async with conn.cursor(row_factory=dict_row) as cur:
                        await cur.execute(
                            "SELECT value, created_at, updated_at FROM store_kv WHERE namespace = %s AND key = %s",
                            (ns_str, key),
                        )
                        row = await cur.fetchone()
                    if row and row["value"]:
                        val = row["value"]
                        if isinstance(val, str):
                            val = json.loads(val)
                        item = Item(
                            value=val,
                            key=key,
                            namespace=op.namespace,
                            created_at=row["created_at"],
                            updated_at=row["updated_at"],
                        )
                        results.append(item)
                    else:
                        results.append(None)

                elif isinstance(op, SearchOp):
                    ns_prefix = _ns_to_str(op.namespace_prefix) if op.namespace_prefix else ""
                    wheres = ["namespace LIKE %s"]
                    params: list[Any] = [ns_prefix + "%"]
                    if op.filter:
                        for k, v in op.filter.items():
                            wheres.append("value @> %s")
                            params.append(json.dumps({k: v}))
                    params.extend([op.limit, op.offset])
                    async with conn.cursor(row_factory=dict_row) as cur:
                        await cur.execute(
                            f"SELECT key, value, namespace, created_at, updated_at FROM store_kv "
                            f"WHERE {' AND '.join(wheres)} ORDER BY updated_at DESC LIMIT %s OFFSET %s",
                            params,
                        )
                        rows = await cur.fetchall()
                    items: list[SearchItem] = []
                    for r in rows:
                        val = r["value"]
                        if isinstance(val, str):
                            val = json.loads(val)
                        ns = tuple(r["namespace"].split("/")) if r["namespace"] else ()
                        items.append(SearchItem(
                            value=val,
                            key=r["key"],
                            namespace=ns,
                            created_at=r["created_at"],
                            updated_at=r["updated_at"],
                        ))
                    # SearchOp returns list[SearchItem]
                    results.append(items)

                elif isinstance(op, ListNamespacesOp):
                    async with conn.cursor(row_factory=dict_row) as cur:
                        await cur.execute(
                            "SELECT DISTINCT namespace FROM store_kv ORDER BY namespace LIMIT %s OFFSET %s",
                            (op.limit, op.offset),
                        )
                        rows = await cur.fetchall()
                    namespaces: list[tuple[str, ...]] = []
                    for r in rows:
                        ns = tuple(r["namespace"].split("/")) if r["namespace"] else ()
                        namespaces.append(ns)
                    # ListNamespacesOp returns list[tuple[str, ...]]
                    results.append(namespaces)

                else:
                    results.append(None)
        return results

    async def start_ttl_sweeper(self) -> None:
        """Background task to delete expired entries."""
        async def _sweep() -> None:
            while True:
                try:
                    from langgraph_runtime_postgres_py.database import _get_pool
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