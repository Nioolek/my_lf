"""Postgres CRUD operations for Assistants, Threads, Runs, and Crons.

Interface matches langgraph_runtime_inmem/ops.py exactly.
"""

from __future__ import annotations

import asyncio
import copy
import json
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

import structlog
from langgraph_sdk import Auth
from psycopg.rows import dict_row
from starlette.exceptions import HTTPException

from langgraph_runtime_postgres_py.database import connect as db_connect
from langgraph_runtime_postgres_py.run_queue import STALE_RUN_TIMEOUT_SECS

logger = structlog.stdlib.get_logger(__name__)


# ---- Helpers ----

def _ensure_uuid(id_: str | UUID | None) -> UUID:
    if isinstance(id_, str):
        return UUID(id_)
    if id_ is None:
        return uuid4()
    return id_


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_dict(row: dict) -> dict:
    """Convert a dict_row result to a plain dict with string keys."""
    return {k: str(v) if isinstance(v, UUID) else v for k, v in row.items()}


def is_jsonb_contained(superset: dict[str, Any], subset: dict[str, Any]) -> bool:
    """Implements Postgres' @> (containment) operator for dictionaries."""
    for key, value in subset.items():
        if key not in superset:
            return False
        if isinstance(value, dict) and isinstance(superset[key], dict):
            if not is_jsonb_contained(superset[key], value):
                return False
        elif superset[key] != value:
            return False
    return True


def _validate_filter_structure(
    filters: Auth.types.FilterType | None,
    nesting_level: int = 0,
) -> None:
    """Validate the structure of filter conditions without checking matches."""
    if nesting_level > 2:
        raise HTTPException(
            status_code=500,
            detail="Your auth handler returned a filter with too many nested operators. The maximum depth for nested operators is 2. Please simplify your filter.",
        )

    if not filters:
        return

    if "$or" in filters:
        or_groups = filters["$or"]
        if not isinstance(or_groups, list) or not len(or_groups) >= 2:
            raise HTTPException(
                status_code=500,
                detail="Your auth handler returned a filter with an invalid $or operator. The $or operator must be a list of at least 2 filter objects.",
            )
        for group in or_groups:
            _validate_filter_structure(group, nesting_level=nesting_level + 1)
        remaining_filters = {k: v for k, v in filters.items() if k != "$or"}
        if remaining_filters:
            _validate_filter_structure(remaining_filters, nesting_level=nesting_level + 1)

    if "$and" in filters:
        and_groups = filters["$and"]
        if not isinstance(and_groups, list) or not len(and_groups) >= 2:
            raise HTTPException(
                status_code=500,
                detail="Your auth handler returned a filter with an invalid $and operator.",
            )
        for group in and_groups:
            _validate_filter_structure(group, nesting_level=nesting_level + 1)
        remaining_filters = {k: v for k, v in filters.items() if k != "$and"}
        if remaining_filters:
            _validate_filter_structure(remaining_filters, nesting_level=nesting_level + 1)


def _check_filter_match(
    metadata: dict,
    filters: Auth.types.FilterType | None,
    nesting_level: int = 0,
) -> bool:
    """Check if metadata matches the filter conditions."""
    if nesting_level > 2:
        raise HTTPException(
            status_code=500,
            detail="Your auth handler returned a filter with too many nested operators.",
        )

    if not filters:
        return True

    if "$or" in filters:
        or_groups = filters["$or"]
        if not isinstance(or_groups, list) or not len(or_groups) >= 2:
            raise HTTPException(status_code=500, detail="Invalid $or operator.")
        for group in or_groups:
            _validate_filter_structure(group, nesting_level=nesting_level + 1)
        or_match = False
        for group in or_groups:
            if _check_filter_match(metadata, group, nesting_level=nesting_level + 1):
                or_match = True
                break
        if not or_match:
            return False
        remaining_filters = {k: v for k, v in filters.items() if k != "$or"}
        if remaining_filters:
            return _check_filter_match(metadata, remaining_filters, nesting_level=nesting_level + 1)
        return True

    if "$and" in filters:
        and_groups = filters["$and"]
        if not isinstance(and_groups, list) or not len(and_groups) >= 2:
            raise HTTPException(status_code=500, detail="Invalid $and operator.")
        for group in and_groups:
            _validate_filter_structure(group, nesting_level=nesting_level + 1)
        for group in and_groups:
            if not _check_filter_match(metadata, group, nesting_level=nesting_level + 1):
                return False
        remaining_filters = {k: v for k, v in filters.items() if k != "$and"}
        if remaining_filters:
            return _check_filter_match(metadata, remaining_filters, nesting_level=nesting_level + 1)
        return True

    for key, value in filters.items():
        if metadata.get(key) != value:
            return False
    return True


def _empty_generator() -> AsyncIterator:
    """Return an empty async iterator."""
    async def _empty():
        if False:
            yield
    return _empty()


# ---- Authenticated Base Class ----

class Authenticated:
    """Base class providing auth context access."""
    resource: Literal["threads", "crons", "assistants"]

    @classmethod
    def _context(
        cls,
        ctx: Auth.types.BaseAuthContext | None,
        action: Literal["create", "read", "update", "delete", "create_run"],
    ) -> Auth.types.AuthContext | None:
        if not ctx:
            return None
        return Auth.types.AuthContext(
            user=ctx.user,
            permissions=ctx.permissions,
            resource=cls.resource,
            action=action,
        )

    @classmethod
    async def handle_event(
        cls,
        ctx: Auth.types.BaseAuthContext | None,
        action: Literal["create", "read", "update", "delete", "search", "create_run"],
        value: Any,
    ) -> Auth.types.FilterType | None:
        from langgraph_api.auth.custom import handle_event
        from langgraph_api.utils import get_auth_ctx

        ctx = ctx or get_auth_ctx()
        if not ctx:
            return None
        return await handle_event(cls._context(ctx, action), value)


# ---- Assistants ----

class Assistants(Authenticated):
    resource = "assistants"

    @staticmethod
    async def search(
        conn,
        *,
        graph_id: str | None = None,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
        limit: int = 10,
        offset: int = 0,
        sort_by: str | None = None,
        sort_order: str | None = None,
        select: list[str] | None = None,
        ctx: Auth.types.BaseAuthContext | None = None,
    ) -> tuple[AsyncIterator[dict], int | None]:
        """Search assistants with pagination."""
        metadata = metadata if metadata is not None else {}
        filters = await Assistants.handle_event(
            ctx,
            "search",
            Auth.types.AssistantsSearch(
                graph_id=graph_id, metadata=metadata, limit=limit, offset=offset
            ),
        )

        if graph_id is not None:
            from langgraph_api.graph import assert_graph_exists
            assert_graph_exists(graph_id)

        wheres = ["1=1"]
        params: list[Any] = []
        if graph_id is not None:
            wheres.append("graph_id = %s")
            params.append(graph_id)
        if metadata:
            wheres.append("metadata @> %s")
            params.append(json.dumps(metadata))
        if name:
            wheres.append("LOWER(name) LIKE LOWER(%s)")
            params.append(f"%{name}%")

        # Count total matching rows (without limit/offset)
        count_rows = await conn.execute(
            f"SELECT COUNT(*) as cnt FROM assistants WHERE {' AND '.join(wheres)}",
            params,
        )
        total_count = count_rows[0]["cnt"] if count_rows else 0

        # Sorting
        sort_by_lower = sort_by.lower() if sort_by else None
        order_clause = "ORDER BY created_at DESC"
        if sort_by_lower in ("assistant_id", "graph_id", "name", "created_at", "updated_at"):
            direction = "ASC" if sort_order and sort_order.upper() == "ASC" else "DESC"
            order_clause = f"ORDER BY {sort_by_lower} {direction}"

        # Fetch limit + 1 for cursor detection
        rows = await conn.execute(
            f"SELECT * FROM assistants WHERE {' AND '.join(wheres)} {order_clause} LIMIT %s OFFSET %s",
            params + [limit + 1, offset],
        )

        has_more = len(rows) > limit
        cursor = offset + limit if has_more else None

        async def _yield():
            for row in rows[:limit]:
                row_dict = _row_to_dict(row)
                if filters and not _check_filter_match(row_dict.get("metadata", {}), filters):
                    continue
                if select:
                    yield {k: v for k, v in row_dict.items() if k in select}
                else:
                    yield row_dict

        return _yield(), cursor

    @staticmethod
    async def get(
        conn,
        assistant_id: UUID | str,
        ctx: Auth.types.BaseAuthContext | None = None,
    ) -> AsyncIterator[dict]:
        """Get an assistant by ID."""
        assistant_id = _ensure_uuid(assistant_id)
        filters = await Assistants.handle_event(
            ctx,
            "read",
            Auth.types.AssistantsRead(assistant_id=assistant_id),
        )

        async def _yield_result():
            rows = await conn.execute(
                "SELECT * FROM assistants WHERE assistant_id = %s",
                (str(assistant_id),),
            )
            if rows:
                row_dict = _row_to_dict(rows[0])
                if not filters or _check_filter_match(row_dict.get("metadata", {}), filters):
                    yield row_dict

        return _yield_result()

    @staticmethod
    async def put(
        conn,
        assistant_id: UUID | str,
        *,
        graph_id: str,
        config: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        if_exists: str = "raise",
        name: str = "",
        description: str | None = None,
        system: bool = False,
        ctx: Auth.types.BaseAuthContext | None = None,
    ) -> AsyncIterator[dict]:
        """Insert or update an assistant."""
        from langgraph_api.graph import assert_graph_exists

        assistant_id = _ensure_uuid(assistant_id)
        config = config or {}
        context = context or {}
        metadata = metadata or {}

        filters = await Assistants.handle_event(
            ctx,
            "create",
            Auth.types.AssistantsCreate(
                assistant_id=assistant_id,
                graph_id=graph_id,
                config=config,
                context=context,
                metadata=metadata,
                name=name,
            ),
        )

        if config.get("configurable") and context:
            raise HTTPException(
                status_code=400,
                detail="Cannot specify both configurable and context.",
            )

        assert_graph_exists(graph_id)

        # Keep config and context synchronized
        if config.get("configurable"):
            context = config["configurable"]
        elif context:
            config["configurable"] = context

        now = datetime.now(UTC)
        existing_rows = await conn.execute(
            "SELECT * FROM assistants WHERE assistant_id = %s",
            (str(assistant_id),),
        )

        if existing_rows:
            existing = _row_to_dict(existing_rows[0])
            if filters and not _check_filter_match(existing.get("metadata", {}), filters):
                raise HTTPException(status_code=409, detail=f"Assistant {assistant_id} already exists")
            if if_exists == "raise":
                raise HTTPException(status_code=409, detail=f"Assistant {assistant_id} already exists")
            elif if_exists == "do_nothing":
                async def _yield_existing():
                    yield existing
                return _yield_existing()

            # Update existing
            await conn.execute(
                """UPDATE assistants SET graph_id = %s, name = %s, description = %s,
                   config = %s, context = %s, metadata = %s, updated_at = %s
                   WHERE assistant_id = %s""",
                (graph_id, name, description, json.dumps(config), json.dumps(context),
                 json.dumps(metadata), now, str(assistant_id)),
            )
            async def _yield_updated():
                yield {**existing, "graph_id": graph_id, "name": name, "description": description,
                       "config": config, "context": context, "metadata": metadata, "updated_at": now}
            return _yield_updated()

        # Insert new
        await conn.execute(
            """INSERT INTO assistants (assistant_id, graph_id, name, description, config, context, metadata, created_at, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (str(assistant_id), graph_id, name, description, json.dumps(config),
             json.dumps(context), json.dumps(metadata), now, now),
        )

        # Record initial version
        await conn.execute(
            """INSERT INTO assistant_versions (assistant_id, version, graph_id, config, context, metadata, name, created_at)
               VALUES (%s, 1, %s, %s, %s, %s, %s, %s)""",
            (str(assistant_id), graph_id, json.dumps(config), json.dumps(context),
             json.dumps(metadata), name, now),
        )

        new_assistant = {
            "assistant_id": assistant_id,
            "graph_id": graph_id,
            "name": name,
            "description": description,
            "config": config,
            "context": context,
            "metadata": metadata,
            "created_at": now,
            "updated_at": now,
            "version": 1,
        }

        async def _yield_new():
            yield new_assistant
        return _yield_new()

    @staticmethod
    async def patch(
        conn,
        assistant_id: UUID,
        *,
        config: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        graph_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        name: str | None = None,
        description: str | None = None,
        ctx: Auth.types.BaseAuthContext | None = None,
    ) -> AsyncIterator[dict]:
        """Update an assistant."""
        from langgraph_api.graph import assert_graph_exists

        assistant_id = _ensure_uuid(assistant_id)
        config = config or {}
        metadata = metadata or {}

        filters = await Assistants.handle_event(
            ctx,
            "update",
            Auth.types.AssistantsUpdate(
                assistant_id=assistant_id,
                graph_id=graph_id,
                config=config,
                context=context,
                metadata=metadata,
                name=name,
            ),
        )

        if config.get("configurable") and context:
            raise HTTPException(
                status_code=400,
                detail="Cannot specify both configurable and context.",
            )

        if graph_id is not None:
            assert_graph_exists(graph_id)

        # Keep config and context synchronized
        if config.get("configurable"):
            context = config["configurable"]
        elif context:
            config["configurable"] = context

        existing_rows = await conn.execute(
            "SELECT * FROM assistants WHERE assistant_id = %s",
            (str(assistant_id),),
        )
        if not existing_rows:
            raise HTTPException(status_code=404, detail=f"Assistant {assistant_id} not found")

        existing = _row_to_dict(existing_rows[0])
        if filters and not _check_filter_match(existing.get("metadata", {}), filters):
            raise HTTPException(status_code=404, detail=f"Assistant {assistant_id} not found")

        now = datetime.now(UTC)

        # Get max version
        version_rows = await conn.execute(
            "SELECT COALESCE(MAX(version), 0) as max_v FROM assistant_versions WHERE assistant_id = %s",
            (str(assistant_id),),
        )
        new_version = (version_rows[0]["max_v"] or 0) + 1

        # Build merged values
        merged_config = config if config else existing.get("config", {})
        merged_context = context if context is not None else existing.get("context", {})
        merged_metadata = {**existing.get("metadata", {}), **metadata} if metadata else existing.get("metadata", {})
        merged_name = name if name is not None else existing.get("name", "")
        merged_description = description if description is not None else existing.get("description")
        merged_graph_id = graph_id if graph_id is not None else existing.get("graph_id")

        # Insert version record
        await conn.execute(
            """INSERT INTO assistant_versions (assistant_id, version, graph_id, config, context, metadata, name, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (str(assistant_id), new_version, merged_graph_id, json.dumps(merged_config),
             json.dumps(merged_context), json.dumps(merged_metadata), merged_name, now),
        )

        # Update assistant
        await conn.execute(
            """UPDATE assistants SET graph_id = %s, name = %s, description = %s,
               config = %s, context = %s, metadata = %s, version = %s, updated_at = %s
               WHERE assistant_id = %s""",
            (merged_graph_id, merged_name, merged_description, json.dumps(merged_config),
             json.dumps(merged_context), json.dumps(merged_metadata), new_version, now, str(assistant_id)),
        )

        updated = {
            **existing,
            "graph_id": merged_graph_id,
            "name": merged_name,
            "description": merged_description,
            "config": merged_config,
            "context": merged_context,
            "metadata": merged_metadata,
            "version": new_version,
            "updated_at": now,
        }

        async def _yield_updated():
            yield updated
        return _yield_updated()

    @staticmethod
    async def delete(
        conn,
        assistant_id: UUID,
        ctx: Auth.types.BaseAuthContext | None = None,
        *,
        delete_threads: bool = False,
    ) -> AsyncIterator[UUID]:
        """Delete an assistant by ID."""
        async with AsyncExitStack() as stack:
            if conn is None:
                conn = await stack.enter_async_context(db_connect())

            assistant_id = _ensure_uuid(assistant_id)
            filters = await Assistants.handle_event(
                ctx,
                "delete",
                Auth.types.AssistantsDelete(assistant_id=assistant_id),
            )

            existing_rows = await conn.execute(
                "SELECT * FROM assistants WHERE assistant_id = %s",
                (str(assistant_id),),
            )
            if not existing_rows:
                raise HTTPException(status_code=404, detail=f"Assistant {assistant_id} not found")

            existing = _row_to_dict(existing_rows[0])
            if filters and not _check_filter_match(existing.get("metadata", {}), filters):
                raise HTTPException(status_code=404, detail=f"Assistant {assistant_id} not found")

            if delete_threads:
                # Find threads with this assistant_id in metadata
                thread_rows = await conn.execute(
                    "SELECT thread_id FROM threads WHERE metadata->>'assistant_id' = %s",
                    (str(assistant_id),),
                )
                for t in thread_rows:
                    try:
                        async for _ in await Threads.delete(conn, t["thread_id"], ctx=ctx):
                            pass
                    except HTTPException:
                        await logger.awarning(
                            "Skipping thread deletion during cascade delete",
                            thread_id=t["thread_id"],
                            assistant_id=assistant_id,
                        )

            # Cancel in-flight runs
            await Runs.cancel(conn, assistant_id=assistant_id, action="interrupt", ctx=ctx)

            # Delete assistant versions
            await conn.execute(
                "DELETE FROM assistant_versions WHERE assistant_id = %s",
                (str(assistant_id),),
            )

            # Delete crons for this assistant
            await conn.execute(
                "DELETE FROM crons WHERE assistant_id = %s",
                (str(assistant_id),),
            )

            # Delete assistant
            await conn.execute(
                "DELETE FROM assistants WHERE assistant_id = %s",
                (str(assistant_id),),
            )

            async def _yield_deleted():
                yield assistant_id

            return _yield_deleted()

    @staticmethod
    async def set_latest(
        conn,
        assistant_id: UUID,
        version: int,
        ctx: Auth.types.BaseAuthContext | None = None,
    ) -> AsyncIterator[dict]:
        """Change the version of an assistant."""
        assistant_id = _ensure_uuid(assistant_id)
        filters = await Assistants.handle_event(
            ctx,
            "update",
            Auth.types.AssistantsUpdate(assistant_id=assistant_id, version=version),
        )

        existing_rows = await conn.execute(
            "SELECT * FROM assistants WHERE assistant_id = %s",
            (str(assistant_id),),
        )
        if not existing_rows:
            raise HTTPException(status_code=404, detail=f"Assistant {assistant_id} not found")

        existing = _row_to_dict(existing_rows[0])
        if filters and not _check_filter_match(existing.get("metadata", {}), filters):
            raise HTTPException(status_code=404, detail=f"Assistant {assistant_id} not found")

        version_rows = await conn.execute(
            "SELECT * FROM assistant_versions WHERE assistant_id = %s AND version = %s",
            (str(assistant_id), version),
        )
        if not version_rows:
            raise HTTPException(status_code=404, detail=f"Version {version} not found for assistant {assistant_id}")

        version_data = _row_to_dict(version_rows[0])
        now = datetime.now(UTC)

        await conn.execute(
            """UPDATE assistants SET graph_id = %s, config = %s, context = %s,
               metadata = %s, name = %s, description = %s, version = %s, updated_at = %s
               WHERE assistant_id = %s""",
            (version_data["graph_id"], json.dumps(version_data.get("config", {})),
             json.dumps(version_data.get("context", {})), json.dumps(version_data.get("metadata", {})),
             version_data.get("name", ""), version_data.get("description"),
             version, now, str(assistant_id)),
        )

        updated = {**existing, **version_data, "version": version, "updated_at": now}

        async def _yield_updated():
            yield updated
        return _yield_updated()

    @staticmethod
    async def get_versions(
        conn,
        assistant_id: UUID,
        metadata: dict[str, Any] | None = None,
        limit: int = 10,
        offset: int = 0,
        ctx: Auth.types.BaseAuthContext | None = None,
    ) -> AsyncIterator[dict]:
        """Get all versions of an assistant."""
        assistant_id = _ensure_uuid(assistant_id)
        metadata = metadata or {}
        filters = await Assistants.handle_event(
            ctx,
            "read",
            Auth.types.AssistantsRead(assistant_id=assistant_id),
        )

        existing_rows = await conn.execute(
            "SELECT * FROM assistants WHERE assistant_id = %s",
            (str(assistant_id),),
        )
        if not existing_rows:
            raise HTTPException(status_code=404, detail=f"Assistant {assistant_id} not found")

        wheres = ["assistant_id = %s"]
        params: list[Any] = [str(assistant_id)]
        if metadata:
            wheres.append("metadata @> %s")
            params.append(json.dumps(metadata))

        rows = await conn.execute(
            f"SELECT * FROM assistant_versions WHERE {' AND '.join(wheres)} ORDER BY version DESC LIMIT %s OFFSET %s",
            params + [limit, offset],
        )

        async def _yield_versions():
            for row in rows:
                row_dict = _row_to_dict(row)
                if filters and not _check_filter_match(row_dict.get("metadata", {}), filters):
                    continue
                yield row_dict

        return _yield_versions()

    @staticmethod
    async def count(
        conn,
        *,
        graph_id: str | None = None,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
        ctx: Auth.types.BaseAuthContext | None = None,
    ) -> int:
        """Get count of assistants."""
        metadata = metadata or {}
        filters = await Assistants.handle_event(
            ctx,
            "search",
            Auth.types.AssistantsSearch(graph_id=graph_id, metadata=metadata, limit=0, offset=0),
        )

        if graph_id is not None:
            from langgraph_api.graph import assert_graph_exists
            assert_graph_exists(graph_id)

        wheres = ["1=1"]
        params: list[Any] = []
        if graph_id is not None:
            wheres.append("graph_id = %s")
            params.append(graph_id)
        if metadata:
            wheres.append("metadata @> %s")
            params.append(json.dumps(metadata))
        if name:
            wheres.append("LOWER(name) LIKE LOWER(%s)")
            params.append(f"%{name}%")

        rows = await conn.execute(
            f"SELECT COUNT(*) as cnt FROM assistants WHERE {' AND '.join(wheres)}",
            params,
        )
        total = rows[0]["cnt"] if rows else 0

        # Apply auth filter (can't do in SQL, need post-filter)
        if filters:
            all_rows = await conn.execute(
                f"SELECT * FROM assistants WHERE {' AND '.join(wheres)}",
                params,
            )
            total = sum(1 for r in all_rows if _check_filter_match(_row_to_dict(r).get("metadata", {}), filters))

        return total


# ---- Threads ----

class Threads(Authenticated):
    resource = "threads"

    @staticmethod
    async def search(
        conn,
        *,
        ids: list[str] | list[UUID] | None = None,
        metadata: dict[str, Any] | None = None,
        values: dict[str, Any] | None = None,
        status: str | None = None,
        limit: int = 10,
        offset: int = 0,
        sort_by: str | None = None,
        sort_order: str | None = None,
        select: list[str] | None = None,
        extract: dict[str, str] | None = None,
        ctx: Auth.types.BaseAuthContext | None = None,
    ) -> tuple[AsyncIterator[dict], int | None]:
        """Search threads with pagination."""
        metadata = metadata or {}
        values = values or {}
        filters = await Threads.handle_event(
            ctx,
            "search",
            Auth.types.ThreadsSearch(
                metadata=metadata,
                values=values,
                status=status,
                limit=limit,
                offset=offset,
            ),
        )

        wheres = ["1=1"]
        params: list[Any] = []

        if ids:
            id_uuids = [_ensure_uuid(i) for i in ids]
            placeholders = ",".join(["%s"] * len(id_uuids))
            wheres.append(f"thread_id IN ({placeholders})")
            params.extend(str(i) for i in id_uuids)

        if metadata:
            wheres.append("metadata @> %s")
            params.append(json.dumps(metadata))

        if values:
            wheres.append("values @> %s")
            params.append(json.dumps(values))

        if status:
            wheres.append("status = %s")
            params.append(status)

        # Sorting
        sort_by_lower = sort_by.lower() if sort_by else None
        order_clause = "ORDER BY updated_at DESC"
        if sort_by_lower in ("thread_id", "created_at", "updated_at", "state_updated_at", "status"):
            direction = "ASC" if sort_order and sort_order.upper() == "ASC" else "DESC"
            order_clause = f"ORDER BY {sort_by_lower} {direction}"

        # Fetch limit + 1
        rows = await conn.execute(
            f"SELECT * FROM threads WHERE {' AND '.join(wheres)} {order_clause} LIMIT %s OFFSET %s",
            params + [limit + 1, offset],
        )

        has_more = len(rows) > limit
        cursor = offset + limit if has_more else None

        async def _yield():
            for row in rows[:limit]:
                row_dict = _row_to_dict(row)
                if filters and not _check_filter_match(row_dict.get("metadata", {}), filters):
                    continue
                row_dict.setdefault("state_updated_at", row_dict.get("updated_at"))
                if select:
                    filtered = {k: v for k, v in row_dict.items() if k in select}
                else:
                    filtered = row_dict
                if extract:
                    filtered["extracted"] = {
                        alias: row_dict.get(path) for alias, path in extract.items()
                    }
                yield filtered

        return _yield(), cursor

    @staticmethod
    async def get(
        conn,
        thread_id: UUID,
        *,
        ctx: Auth.types.BaseAuthContext | None = None,
        include_ttl: bool = False,
        read_mask_paths: list[str] | None = None,
    ) -> AsyncIterator[dict]:
        """Get a thread by ID."""
        thread_id = _ensure_uuid(thread_id)
        filters = await Threads.handle_event(
            ctx,
            "read",
            Auth.types.ThreadsRead(thread_id=thread_id),
        )

        async def _yield_result():
            rows = await conn.execute(
                "SELECT * FROM threads WHERE thread_id = %s",
                (str(thread_id),),
            )
            if not rows:
                raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
            row_dict = _row_to_dict(rows[0])
            if filters and not _check_filter_match(row_dict.get("metadata", {}), filters):
                raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
            row_dict.setdefault("state_updated_at", row_dict.get("updated_at"))
            yield row_dict

        return _yield_result()

    @staticmethod
    async def put(
        conn,
        thread_id: UUID | str,
        *,
        metadata: dict[str, Any] | None = None,
        if_exists: str = "raise",
        ttl: dict[str, Any] | None = None,
        ctx: Auth.types.BaseAuthContext | None = None,
    ) -> AsyncIterator[dict]:
        """Insert or update a thread."""
        thread_id = _ensure_uuid(thread_id)
        metadata = metadata or {}

        filters = await Threads.handle_event(
            ctx,
            "create",
            Auth.types.ThreadsCreate(thread_id=thread_id, metadata=metadata, if_exists=if_exists),
        )

        existing_rows = await conn.execute(
            "SELECT * FROM threads WHERE thread_id = %s",
            (str(thread_id),),
        )

        if existing_rows:
            existing = _row_to_dict(existing_rows[0])
            if filters and not _check_filter_match(existing.get("metadata", {}), filters):
                raise HTTPException(status_code=409, detail=f"Thread {thread_id} already exists")
            if if_exists == "raise":
                raise HTTPException(status_code=409, detail=f"Thread {thread_id} already exists")
            elif if_exists == "do_nothing":
                async def _yield_existing():
                    yield existing
                return _yield_existing()

        now = datetime.now(UTC)
        expires_at = None
        if ttl:
            ttl_seconds = ttl.get("seconds", 0)
            if ttl_seconds > 0:
                from datetime import timedelta
                expires_at = now + timedelta(seconds=ttl_seconds)

        if existing_rows and if_exists not in ("raise", "do_nothing"):
            # Update existing
            merged_metadata = {**existing.get("metadata", {}), **metadata}
            await conn.execute(
                """UPDATE threads SET metadata = %s, updated_at = %s, expires_at = COALESCE(%s, expires_at)
                   WHERE thread_id = %s""",
                (json.dumps(merged_metadata), now, expires_at, str(thread_id)),
            )
            updated = {**existing, "metadata": merged_metadata, "updated_at": now}
            if expires_at:
                updated["expires_at"] = expires_at
            async def _yield_updated():
                yield updated
            return _yield_updated()

        # Insert new
        await conn.execute(
            """INSERT INTO threads (thread_id, metadata, status, created_at, updated_at, expires_at)
               VALUES (%s, %s, 'idle', %s, %s, %s)""",
            (str(thread_id), json.dumps(metadata), now, now, expires_at),
        )

        new_thread = {
            "thread_id": thread_id,
            "metadata": metadata,
            "status": "idle",
            "created_at": now,
            "updated_at": now,
            "state_updated_at": now,
            "config": {},
            "values": None,
        }
        if expires_at:
            new_thread["expires_at"] = expires_at

        async def _yield_new():
            yield new_thread
        return _yield_new()

    @staticmethod
    async def patch(
        conn,
        thread_id: UUID,
        *,
        metadata: dict[str, Any] | None = None,
        ttl: dict[str, Any] | None = None,
        ctx: Auth.types.BaseAuthContext | None = None,
        read_mask_paths: list[str] | None = None,
    ) -> AsyncIterator[dict]:
        """Update a thread."""
        thread_id = _ensure_uuid(thread_id)
        metadata = metadata or {}

        filters = await Threads.handle_event(
            ctx,
            "update",
            Auth.types.ThreadsUpdate(thread_id=thread_id, metadata=metadata),
        )

        existing_rows = await conn.execute(
            "SELECT * FROM threads WHERE thread_id = %s",
            (str(thread_id),),
        )
        if not existing_rows:
            raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

        existing = _row_to_dict(existing_rows[0])
        if filters and not _check_filter_match(existing.get("metadata", {}), filters):
            raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

        now = datetime.now(UTC)
        merged_metadata = {**existing.get("metadata", {}), **metadata}

        expires_at = existing.get("expires_at")
        if ttl:
            ttl_seconds = ttl.get("seconds", 0)
            if ttl_seconds > 0:
                from datetime import timedelta
                expires_at = now + timedelta(seconds=ttl_seconds)

        await conn.execute(
            """UPDATE threads SET metadata = %s, updated_at = %s, expires_at = COALESCE(%s, expires_at)
               WHERE thread_id = %s""",
            (json.dumps(merged_metadata), now, expires_at, str(thread_id)),
        )

        updated = {**existing, "metadata": merged_metadata, "updated_at": now}
        if expires_at:
            updated["expires_at"] = expires_at

        async def _yield_updated():
            yield updated
        return _yield_updated()

    @staticmethod
    async def set_status(
        conn,
        thread_id: UUID,
        checkpoint: dict[str, Any] | None,
        exception: BaseException | None,
    ) -> None:
        """Set the status of a thread (worker internal)."""
        from langgraph_api.serde import json_dumpb, json_loads

        thread_id = _ensure_uuid(thread_id)

        # Check for pending runs
        pending_rows = await conn.execute(
            "SELECT COUNT(*) as cnt FROM runs WHERE thread_id = %s AND status IN ('pending', 'running')",
            (str(thread_id),),
        )
        has_pending = pending_rows and pending_rows[0]["cnt"] > 0

        if exception:
            status = "error"
        elif checkpoint and checkpoint.get("next"):
            status = "interrupted"
        else:
            status = "idle"

        if has_pending:
            status = "busy"

        now = datetime.now(UTC)
        interrupts = {}
        if checkpoint:
            for task in checkpoint.get("tasks", []):
                if task.get("interrupts"):
                    interrupts[task["id"]] = list(task["interrupts"])

        error_data = json_loads(json_dumpb(exception)) if exception else None

        update_values = {
            "status": status,
            "interrupts": json.dumps(interrupts),
            "error": json.dumps(error_data) if error_data else None,
            "updated_at": now,
            "state_updated_at": now,
        }

        sets = ["status = %s", "interrupts = %s", "updated_at = %s", "state_updated_at = %s"]
        params = [status, update_values["interrupts"], now, now]
        if error_data:
            sets.append("error = %s")
            params.append(update_values["error"])
        else:
            sets.append("error = NULL")

        if checkpoint is not None:
            sets.append("values = %s")
            params.append(json.dumps(checkpoint.get("values", {})))

        params.append(str(thread_id))
        await conn.execute(
            f"UPDATE threads SET {', '.join(sets)} WHERE thread_id = %s",
            params,
        )

    @staticmethod
    async def set_joint_status(
        conn,
        thread_id: UUID,
        run_id: UUID,
        run_status: str,
        graph_id: str,
        checkpoint: dict[str, Any] | None = None,
        exception: BaseException | None = None,
    ) -> None:
        """Set the status of both thread and run atomically (worker internal)."""
        from langgraph_api.errors import UserInterrupt, UserRollback
        from langgraph_api.serde import json_dumpb, json_loads

        thread_id = _ensure_uuid(thread_id)
        run_id = _ensure_uuid(run_id)

        # Check for pending runs
        pending_rows = await conn.execute(
            "SELECT COUNT(*) as cnt FROM runs WHERE thread_id = %s AND status IN ('pending', 'running') AND run_id != %s",
            (str(thread_id), str(run_id)),
        )
        has_other_pending = pending_rows and pending_rows[0]["cnt"] > 0

        if run_status == "rollback":
            # Delete the run
            await conn.execute(
                "DELETE FROM runs WHERE run_id = %s",
                (str(run_id),),
            )
        else:
            # Update run status
            now = datetime.now(UTC)
            await conn.execute(
                "UPDATE runs SET status = %s, updated_at = %s WHERE run_id = %s",
                (run_status, now, str(run_id)),
            )

        # Determine thread status
        has_next = bool(checkpoint and checkpoint.get("next"))
        if exception and not isinstance(exception, UserInterrupt | UserRollback):
            base_status = "error"
        elif has_next:
            base_status = "interrupted"
        else:
            base_status = "idle"

        if run_status in ("pending", "running") or has_other_pending:
            final_status = "busy"
        else:
            final_status = base_status

        interrupts = {}
        if checkpoint:
            for task in checkpoint.get("tasks", []):
                if task.get("interrupts"):
                    interrupts[task["id"]] = list(task["interrupts"])

        now = datetime.now(UTC)
        error_data = json_loads(json_dumpb(exception)) if exception else None

        # Update thread with graph_id in metadata
        thread_rows = await conn.execute(
            "SELECT metadata FROM threads WHERE thread_id = %s",
            (str(thread_id),),
        )
        if thread_rows:
            existing_metadata = thread_rows[0].get("metadata", {}) or {}
            existing_metadata["graph_id"] = graph_id

            sets = ["status = %s", "interrupts = %s", "metadata = %s", "updated_at = %s", "state_updated_at = %s"]
            params = [final_status, json.dumps(interrupts), json.dumps(existing_metadata), now, now]

            if error_data:
                sets.append("error = %s")
                params.append(json.dumps(error_data))
            else:
                sets.append("error = NULL")

            if checkpoint is not None:
                sets.append("values = %s")
                params.append(json.dumps(checkpoint.get("values", {})))

            params.append(str(thread_id))
            await conn.execute(
                f"UPDATE threads SET {', '.join(sets)} WHERE thread_id = %s",
                params,
            )

    @staticmethod
    async def delete(
        conn,
        thread_id: UUID,
        ctx: Auth.types.BaseAuthContext | None = None,
    ) -> AsyncIterator[UUID]:
        """Delete a thread by ID and cascade delete all associated runs."""
        thread_id = _ensure_uuid(thread_id)
        filters = await Threads.handle_event(
            ctx,
            "delete",
            Auth.types.ThreadsDelete(thread_id=thread_id),
        )

        existing_rows = await conn.execute(
            "SELECT * FROM threads WHERE thread_id = %s",
            (str(thread_id),),
        )
        if not existing_rows:
            raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

        existing = _row_to_dict(existing_rows[0])
        if filters and not _check_filter_match(existing.get("metadata", {}), filters):
            raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

        # Delete runs
        await conn.execute(
            "DELETE FROM runs WHERE thread_id = %s",
            (str(thread_id),),
        )

        # Delete crons
        await conn.execute(
            "DELETE FROM crons WHERE thread_id = %s",
            (str(thread_id),),
        )

        # Delete checkpoints
        from langgraph_runtime_postgres_py.checkpoint import Checkpointer
        try:
            checkpointer = Checkpointer()
            await checkpointer.adelete_thread(str(thread_id))
        except Exception as e:
            logger.warning(
                "Failed to delete checkpoint for thread",
                thread_id=thread_id,
                error=str(e),
            )

        # Delete thread
        await conn.execute(
            "DELETE FROM threads WHERE thread_id = %s",
            (str(thread_id),),
        )

        async def _yield_deleted():
            yield thread_id

        return _yield_deleted()

    @staticmethod
    async def count(
        conn,
        *,
        metadata: dict[str, Any] | None = None,
        values: dict[str, Any] | None = None,
        status: str | None = None,
        ctx: Auth.types.BaseAuthContext | None = None,
    ) -> int:
        """Get count of threads."""
        metadata = metadata or {}
        values = values or {}
        filters = await Threads.handle_event(
            ctx,
            "search",
            Auth.types.ThreadsSearch(metadata=metadata, values=values, status=status, limit=0, offset=0),
        )

        wheres = ["1=1"]
        params: list[Any] = []
        if metadata:
            wheres.append("metadata @> %s")
            params.append(json.dumps(metadata))
        if values:
            wheres.append("values @> %s")
            params.append(json.dumps(values))
        if status:
            wheres.append("status = %s")
            params.append(status)

        rows = await conn.execute(
            f"SELECT COUNT(*) as cnt FROM threads WHERE {' AND '.join(wheres)}",
            params,
        )
        total = rows[0]["cnt"] if rows else 0

        if filters:
            all_rows = await conn.execute(
                f"SELECT * FROM threads WHERE {' AND '.join(wheres)}",
                params,
            )
            total = sum(1 for r in all_rows if _check_filter_match(_row_to_dict(r).get("metadata", {}), filters))

        return total

    class State(Authenticated):
        """Thread state operations."""
        resource = "threads"

        @staticmethod
        async def get(
            conn,
            config: dict[str, Any],
            subgraphs: bool = False,
            ctx: Auth.types.BaseAuthContext | None = None,
        ) -> dict[str, Any]:
            """Get state for a thread."""
            from langgraph.pregel.debug import StateSnapshot
            from langgraph_api.graph import get_graph
            from langgraph_api.store import get_store
            from langgraph_runtime_postgres_py.checkpoint import Checkpointer

            thread_id = _ensure_uuid(config.get("configurable", {}).get("thread_id"))

            # Auth check
            filters = await Threads.handle_event(
                ctx,
                "read",
                Auth.types.ThreadsRead(thread_id=thread_id),
            )

            thread_rows = await conn.execute(
                "SELECT * FROM threads WHERE thread_id = %s",
                (str(thread_id),),
            )
            if not thread_rows:
                return StateSnapshot(
                    values={},
                    next=[],
                    config=None,
                    metadata=None,
                    created_at=None,
                    parent_config=None,
                    tasks=tuple(),
                )

            thread = _row_to_dict(thread_rows[0])
            if filters and not _check_filter_match(thread.get("metadata", {}), filters):
                return StateSnapshot(
                    values={},
                    next=[],
                    config=None,
                    metadata=None,
                    created_at=None,
                    parent_config=None,
                    tasks=tuple(),
                )

            thread_metadata = thread.get("metadata", {})
            graph_id = thread_metadata.get("graph_id")

            if not graph_id:
                # Try to get from runs
                run_rows = await conn.execute(
                    "SELECT kwargs FROM runs WHERE thread_id = %s LIMIT 1",
                    (str(thread_id),),
                )
                if run_rows:
                    kwargs = run_rows[0].get("kwargs", {}) or {}
                    graph_id = kwargs.get("config", {}).get("configurable", {}).get("graph_id")

            if not graph_id:
                return StateSnapshot(
                    values={},
                    next=[],
                    config=None,
                    metadata=None,
                    created_at=None,
                    parent_config=None,
                    tasks=tuple(),
                )

            checkpointer = Checkpointer()
            thread_config = thread.get("config", {})
            thread_config = {
                **thread_config,
                "configurable": {
                    **thread_config.get("configurable", {}),
                    **config.get("configurable", {}),
                },
            }

            async with get_graph(
                graph_id,
                thread_config,
                checkpointer=checkpointer,
                store=(await get_store()),
                access_context="threads.read",
            ) as graph:
                result = await graph.aget_state(config, subgraphs=subgraphs)
                return result

        @staticmethod
        async def post(
            conn,
            config: dict[str, Any],
            values: dict[str, Any] | None,
            as_node: str | None = None,
            ctx: Auth.types.BaseAuthContext | None = None,
        ) -> dict[str, Any]:
            """Add state to a thread."""
            from langgraph_api.graph import get_graph
            from langgraph_api.store import get_store
            from langgraph_api.utils import fetchone
            from langgraph_runtime_postgres_py.checkpoint import Checkpointer

            thread_id = _ensure_uuid(config.get("configurable", {}).get("thread_id"))
            filters = await Threads.handle_event(
                ctx,
                "update",
                Auth.types.ThreadsUpdate(thread_id=thread_id),
            )

            thread_iter = await Threads.get(conn, thread_id, ctx=ctx)
            thread = await fetchone(thread_iter, not_found_detail=f"Thread {thread_id} not found.")
            if not thread:
                raise HTTPException(status_code=404, detail="Thread not found")
            if not _check_filter_match(thread.get("metadata", {}), filters):
                raise HTTPException(status_code=403, detail="Forbidden")

            # Check for in-flight runs
            pending_rows = await conn.execute(
                "SELECT run_id FROM runs WHERE thread_id = %s AND status IN ('pending', 'running')",
                (str(thread_id),),
            )
            if pending_rows:
                raise HTTPException(
                    status_code=409,
                    detail=f"Thread {thread_id} has in-flight runs",
                )

            thread_metadata = thread.get("metadata", {})
            graph_id = thread_metadata.get("graph_id")

            if not graph_id:
                run_rows = await conn.execute(
                    "SELECT kwargs FROM runs WHERE thread_id = %s LIMIT 1",
                    (str(thread_id),),
                )
                if run_rows:
                    kwargs = run_rows[0].get("kwargs", {}) or {}
                    graph_id = kwargs.get("config", {}).get("configurable", {}).get("graph_id")

            if not graph_id:
                raise HTTPException(
                    status_code=400,
                    detail=f"Thread '{thread_id}' has no assigned graph ID.",
                )

            config.setdefault("configurable", {})["graph_id"] = graph_id

            checkpointer = Checkpointer()
            thread_config = thread.get("config", {})
            thread_config = {
                **thread_config,
                "configurable": {
                    **thread_config.get("configurable", {}),
                    **config.get("configurable", {}),
                },
            }

            async with get_graph(
                graph_id,
                thread_config,
                checkpointer=checkpointer,
                store=(await get_store()),
                access_context="threads.update",
            ) as graph:
                next_config = await graph.aupdate_state(config, values, as_node=as_node)

                # Get current state
                state = await Threads.State.get(conn, config, subgraphs=False, ctx=ctx)

                # Update thread status
                await Threads.set_status(
                    conn,
                    thread_id,
                    {
                        "next": list(state.next),
                        "values": state.values,
                        "tasks": [
                            {"id": t.id, "interrupts": list(t.interrupts)}
                            for t in state.tasks
                        ],
                    },
                    None,
                )

                return {
                    "checkpoint": next_config.get("configurable", {}),
                    "configurable": next_config.get("configurable", {}),
                    "checkpoint_id": next_config.get("configurable", {}).get("checkpoint_id"),
                }

        @staticmethod
        async def list(
            conn,
            *,
            config: dict[str, Any],
            limit: int = 10,
            before: str | dict[str, Any] | None = None,
            metadata: dict[str, Any] | None = None,
            ctx: Auth.types.BaseAuthContext | None = None,
        ) -> list[dict[str, Any]]:
            """Get the history of a thread."""
            from langgraph_api.graph import get_graph
            from langgraph_api.store import get_store
            from langgraph_api.utils import fetchone
            from langgraph_runtime_postgres_py.checkpoint import Checkpointer

            thread_id = _ensure_uuid(config.get("configurable", {}).get("thread_id"))
            filters = await Threads.handle_event(
                ctx,
                "read",
                Auth.types.ThreadsRead(thread_id=thread_id),
            )

            thread_iter = await Threads.get(conn, str(thread_id), ctx=ctx)
            thread = await fetchone(thread_iter)
            if not thread:
                return []

            if not _check_filter_match(thread.get("metadata", {}), filters):
                return []

            thread_metadata = thread.get("metadata", {})
            graph_id = thread_metadata.get("graph_id")

            if not graph_id:
                return []

            checkpointer = Checkpointer()
            thread_config = thread.get("config", {})
            thread_config = {
                **thread_config,
                "configurable": {
                    **thread_config.get("configurable", {}),
                    **config.get("configurable", {}),
                },
            }

            before_param = None
            if before:
                if isinstance(before, str):
                    before_param = {"configurable": {"checkpoint_id": before}}
                else:
                    before_param = before

            async with get_graph(
                graph_id,
                thread_config,
                checkpointer=checkpointer,
                store=(await get_store()),
                access_context="threads.read",
            ) as graph:
                states = [
                    state
                    async for state in graph.aget_state_history(
                        config, limit=limit, filter=metadata, before=before_param
                    )
                ]
                return states

    class Stream(Authenticated):
        """Thread stream operations."""
        resource = "threads"

        @staticmethod
        async def subscribe(
            conn,
            thread_id: UUID,
            seen_runs: set[UUID],
        ) -> list[tuple[UUID, asyncio.Queue]]:
            """Subscribe to the thread stream, creating queues for unseen runs."""
            from langgraph_runtime_inmem.inmem_stream import ContextQueue, get_stream_manager

            thread_id = _ensure_uuid(thread_id)
            stream_manager = get_stream_manager()
            queues = []

            # Add thread stream queue
            if thread_id not in seen_runs:
                queue = await stream_manager.add_thread_stream(thread_id)
                queues.append((thread_id, queue))
                seen_runs.add(thread_id)

            # Get runs for this thread and add queues for unseen ones
            run_rows = await conn.execute(
                "SELECT run_id FROM runs WHERE thread_id = %s",
                (str(thread_id),),
            )
            for row in run_rows:
                run_id = row["run_id"]
                if run_id not in seen_runs:
                    queue = await stream_manager.add_queue(run_id, thread_id)
                    queues.append((run_id, queue))
                    seen_runs.add(run_id)

            return queues

        @staticmethod
        async def join(
            thread_id: UUID,
            *,
            last_event_id: str | None = None,
            stream_modes: list[str],
            ctx: Auth.types.BaseAuthContext | None = None,
        ) -> AsyncIterator[tuple[bytes, bytes, bytes | None]]:
            """Stream the thread output."""
            from langgraph_runtime_postgres_py.run_queue import get_redis

            await Threads.Stream.check_thread_stream_auth(thread_id, ctx)

            redis = await get_redis()
            async with redis.pubsub() as pubsub:
                await pubsub.subscribe(f"thread:{thread_id}:stream")

                async with db_connect() as conn:
                    while True:
                        message = await pubsub.get_message(timeout=0.5, ignore_subscribe_messages=True)
                        if message:
                            # Decode and yield
                            event = message.get("data", b"")
                            if isinstance(event, bytes):
                                yield event, b"", None
                        else:
                            # Check if thread still exists
                            rows = await conn.execute(
                                "SELECT status FROM threads WHERE thread_id = %s",
                                (str(thread_id),),
                            )
                            if not rows:
                                break
                            await asyncio.sleep(0.02)

        @staticmethod
        async def check_thread_stream_auth(
            thread_id: UUID,
            ctx: Auth.types.BaseAuthContext | None = None,
        ) -> None:
            """Check auth for thread stream."""
            async with db_connect() as conn:
                filters = await Threads.Stream.handle_event(
                    ctx,
                    "read",
                    Auth.types.ThreadsRead(thread_id=thread_id),
                )
                if filters:
                    rows = await conn.execute(
                        "SELECT metadata FROM threads WHERE thread_id = %s",
                        (str(thread_id),),
                    )
                    if not rows:
                        raise HTTPException(status_code=404, detail="Thread not found")
                    metadata = rows[0].get("metadata", {})
                    if not _check_filter_match(metadata, filters):
                        raise HTTPException(status_code=404, detail="Thread not found")

        @staticmethod
        async def publish(
            thread_id: UUID | str,
            event: str,
            message: bytes,
        ) -> None:
            """Publish a thread-level event."""
            from langgraph_runtime_postgres_py.run_queue import get_redis

            redis = await get_redis()
            await redis.publish(f"thread:{thread_id}:stream", message)


# ---- Runs ----

class Runs(Authenticated):
    resource = "threads"

    @staticmethod
    async def stats(conn) -> dict[str, Any]:
        """Get stats about the queue."""
        pending_rows = await conn.execute(
            "SELECT COUNT(*) as cnt, MAX(created_at) as oldest FROM runs WHERE status = 'pending'"
        )
        running_rows = await conn.execute(
            "SELECT COUNT(*) as cnt FROM runs WHERE status = 'running'"
        )

        pending_count = pending_rows[0]["cnt"] if pending_rows else 0
        running_count = running_rows[0]["cnt"] if running_rows else 0

        now = datetime.now(UTC)
        max_wait = None
        med_wait = None
        if pending_rows and pending_rows[0].get("oldest"):
            oldest = pending_rows[0]["oldest"]
            if oldest.tzinfo is None:
                oldest = oldest.replace(tzinfo=UTC)
            max_wait = (now - oldest).total_seconds()

        return {
            "n_pending": pending_count,
            "n_running": running_count,
            "pending_runs_wait_time_max_secs": max_wait,
            "pending_runs_wait_time_med_secs": med_wait,
            "pending_unblocked_runs_wait_time_max_secs": None,
        }

    @staticmethod
    async def pool_stats() -> dict[str, Any]:
        """Get pool stats (not applicable for postgres)."""
        from langgraph_runtime_postgres_py.database import pool_stats
        return pool_stats()

    @staticmethod
    async def put(
        conn,
        assistant_id: UUID,
        kwargs: dict[str, Any],
        *,
        thread_id: UUID | None = None,
        user_id: str | None = None,
        run_id: UUID | None = None,
        status: str = "pending",
        metadata: dict[str, Any] | None = None,
        prevent_insert_if_inflight: bool = False,
        multitask_strategy: str = "reject",
        if_not_exists: str = "reject",
        after_seconds: int = 0,
        ctx: Auth.types.BaseAuthContext | None = None,
    ) -> AsyncIterator[dict]:
        """Create a run."""
        assistant_id = _ensure_uuid(assistant_id)
        thread_id = _ensure_uuid(thread_id) if thread_id else None
        run_id = _ensure_uuid(run_id) if run_id else uuid4()
        metadata = metadata or {}
        config = kwargs.get("config", {})
        temporary = kwargs.get("temporary", False)

        # Get assistant
        assistant_rows = await conn.execute(
            "SELECT * FROM assistants WHERE assistant_id = %s",
            (str(assistant_id),),
        )
        if not assistant_rows:
            return _empty_generator()

        assistant = _row_to_dict(assistant_rows[0])

        # Auth check
        filters = await Runs.handle_event(
            ctx,
            "create_run",
            Auth.types.RunsCreate(
                thread_id=None if temporary else thread_id,
                assistant_id=assistant_id,
                run_id=run_id,
                status=status,
                metadata=metadata,
                prevent_insert_if_inflight=prevent_insert_if_inflight,
                multitask_strategy=multitask_strategy,
                if_not_exists=if_not_exists,
                after_seconds=after_seconds,
                kwargs=kwargs,
            ),
        )

        # Check for existing thread
        existing_thread = None
        if thread_id:
            thread_rows = await conn.execute(
                "SELECT * FROM threads WHERE thread_id = %s",
                (str(thread_id),),
            )
            if thread_rows:
                existing_thread = _row_to_dict(thread_rows[0])

        if existing_thread and filters:
            if not _check_filter_match(existing_thread.get("metadata", {}), filters):
                return _empty_generator()

        # Handle thread creation
        if not existing_thread and (thread_id is None or if_not_exists == "create"):
            if thread_id is None:
                thread_id = uuid4()

            now = datetime.now(UTC)
            thread_metadata = {
                "graph_id": assistant["graph_id"],
                "assistant_id": str(assistant_id),
                **(config.get("metadata") or {}),
                **metadata,
            }

            await conn.execute(
                """INSERT INTO threads (thread_id, metadata, status, config, created_at, updated_at)
                   VALUES (%s, %s, 'busy', %s, %s, %s)""",
                (str(thread_id), json.dumps(thread_metadata), json.dumps(config), now, now),
            )
        elif existing_thread:
            # Update thread status
            now = datetime.now(UTC)
            merged_metadata = {**existing_thread.get("metadata", {}), "graph_id": assistant["graph_id"], "assistant_id": str(assistant_id)}
            await conn.execute(
                """UPDATE threads SET status = 'busy', metadata = %s, updated_at = %s WHERE thread_id = %s""",
                (json.dumps(merged_metadata), now, str(thread_id)),
            )
        else:
            return _empty_generator()

        # Check for in-flight runs
        inflight_rows = await conn.execute(
            "SELECT * FROM runs WHERE thread_id = %s AND status IN ('pending', 'running')",
            (str(thread_id),),
        )
        inflight_runs = [_row_to_dict(r) for r in inflight_rows]

        if prevent_insert_if_inflight and inflight_runs:
            async def _return_inflight():
                for run in inflight_runs:
                    yield run
            return _return_inflight()

        # Create run
        configurable = {
            **(assistant.get("config", {}).get("configurable", {})),
            **(existing_thread.get("config", {}).get("configurable", {}) if existing_thread else {}),
            **config.get("configurable", {}),
            "run_id": str(run_id),
            "thread_id": str(thread_id),
            "graph_id": assistant["graph_id"],
            "assistant_id": str(assistant_id),
            "user_id": user_id or config.get("configurable", {}).get("user_id"),
        }

        merged_config = {
            **assistant.get("config", {}),
            **config,
            "configurable": configurable,
        }

        merged_metadata = {
            **assistant.get("metadata", {}),
            **(existing_thread.get("metadata", {}) if existing_thread else {}),
            **(config.get("metadata") or {}),
            **metadata,
            "assistant_id": str(assistant_id),
        }

        now = datetime.now(UTC)
        created_at = now
        if after_seconds > 0:
            from datetime import timedelta
            created_at = now + timedelta(seconds=after_seconds)

        merged_kwargs = {
            **kwargs,
            "config": merged_config,
            "context": {**assistant.get("context", {}), **kwargs.get("context", {})},
        }

        await conn.execute(
            """INSERT INTO runs (run_id, thread_id, assistant_id, status, metadata, kwargs, multitask_strategy, created_at, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (str(run_id), str(thread_id), str(assistant_id), status,
             json.dumps(merged_metadata), json.dumps(merged_kwargs), multitask_strategy, created_at, now),
        )

        new_run = {
            "run_id": run_id,
            "thread_id": thread_id,
            "assistant_id": assistant_id,
            "status": status,
            "metadata": merged_metadata,
            "kwargs": merged_kwargs,
            "multitask_strategy": multitask_strategy,
            "created_at": created_at,
            "updated_at": now,
        }

        async def _yield_new():
            yield new_run
            for r in inflight_runs:
                yield r

        return _yield_new()

    @staticmethod
    async def get(
        conn,
        run_id: UUID,
        *,
        thread_id: UUID,
        ctx: Auth.types.BaseAuthContext | None = None,
    ) -> AsyncIterator[dict]:
        """Get a run by ID."""
        run_id = _ensure_uuid(run_id)
        thread_id = _ensure_uuid(thread_id)

        filters = await Runs.handle_event(
            ctx,
            "read",
            Auth.types.ThreadsRead(thread_id=thread_id),
        )

        async def _yield_result():
            rows = await conn.execute(
                "SELECT * FROM runs WHERE run_id = %s AND thread_id = %s",
                (str(run_id), str(thread_id)),
            )
            if rows:
                row_dict = _row_to_dict(rows[0])
                if filters:
                    thread_rows = await conn.execute(
                        "SELECT metadata FROM threads WHERE thread_id = %s",
                        (str(thread_id),),
                    )
                    if thread_rows:
                        thread_metadata = thread_rows[0].get("metadata", {})
                        if not _check_filter_match(thread_metadata, filters):
                            return
                yield row_dict

        return _yield_result()

    @staticmethod
    async def delete(
        conn,
        run_id: UUID,
        *,
        thread_id: UUID,
        ctx: Auth.types.BaseAuthContext | None = None,
    ) -> AsyncIterator[UUID]:
        """Delete a run by ID."""
        run_id = _ensure_uuid(run_id)
        thread_id = _ensure_uuid(thread_id)

        filters = await Runs.handle_event(
            ctx,
            "delete",
            Auth.types.ThreadsDelete(run_id=run_id, thread_id=thread_id),
        )

        if filters:
            thread_rows = await conn.execute(
                "SELECT metadata FROM threads WHERE thread_id = %s",
                (str(thread_id),),
            )
            if thread_rows:
                if not _check_filter_match(thread_rows[0].get("metadata", {}), filters):
                    return _empty_generator()

        # Delete checkpoints for this run
        from langgraph_runtime_postgres_py.checkpoint import Checkpointer
        try:
            checkpointer = Checkpointer()
            await checkpointer.adelete_for_runs([str(run_id)])
        except Exception as e:
            logger.warning(
                "Failed to delete checkpoint for run",
                run_id=run_id,
                error=str(e),
            )

        existing_rows = await conn.execute(
            "SELECT run_id FROM runs WHERE run_id = %s AND thread_id = %s",
            (str(run_id), str(thread_id)),
        )
        if not existing_rows:
            raise HTTPException(status_code=404, detail="Run not found")

        await conn.execute(
            "DELETE FROM runs WHERE run_id = %s",
            (str(run_id),),
        )

        async def _yield_deleted():
            yield run_id

        return _yield_deleted()

    @staticmethod
    async def cancel(
        conn,
        run_ids: list[UUID | str] | None = None,
        *,
        action: Literal["interrupt", "rollback"] = "interrupt",
        thread_id: UUID | None = None,
        status: Literal["pending", "running", "all"] | None = None,
        assistant_id: UUID | None = None,
        ctx: Auth.types.BaseAuthContext | None = None,
    ) -> None:
        """Cancel runs."""
        async with AsyncExitStack() as stack:
            if conn is None:
                conn = await stack.enter_async_context(db_connect())

            # Validate arguments
            if assistant_id is not None:
                if thread_id is not None or run_ids is not None or status is not None:
                    raise HTTPException(
                        status_code=422,
                        detail="Cannot specify 'thread_id', 'run_ids', or 'status' when using 'assistant_id'",
                    )
                assistant_id = _ensure_uuid(assistant_id)
            elif status is not None:
                if thread_id is not None or run_ids is not None:
                    raise HTTPException(
                        status_code=422,
                        detail="Cannot specify 'thread_id' or 'run_ids' when using 'status'",
                    )
            else:
                if thread_id is None or run_ids is None:
                    raise HTTPException(
                        status_code=422,
                        detail="Must provide either a status, an assistant_id, or both 'thread_id' and 'run_ids'",
                    )

            if run_ids is not None:
                run_ids = [_ensure_uuid(rid) for rid in run_ids]
            if thread_id is not None:
                thread_id = _ensure_uuid(thread_id)

            filters = await Runs.handle_event(
                ctx,
                "update",
                Auth.types.ThreadsUpdate(
                    thread_id=thread_id,
                    action=action,
                    metadata={"run_ids": [str(r) for r in run_ids] if run_ids else None, "status": status},
                ),
            )

            status_list: tuple[str, ...] = ()
            if status == "all":
                status_list = ("pending", "running")
            elif status in ("pending", "running"):
                status_list = (status,)

            # Build query to find matching runs
            wheres = ["1=1"]
            params: list[Any] = []

            if assistant_id is not None:
                wheres.append("assistant_id = %s AND status IN ('pending', 'running')")
                params.append(str(assistant_id))
            elif status_list:
                placeholders = ",".join(["%s"] * len(status_list))
                wheres.append(f"status IN ({placeholders})")
                params.extend(status_list)
            else:
                wheres.append("thread_id = %s AND run_id IN (%s)")
                params.append(str(thread_id))
                placeholders = ",".join(["%s"] * len(run_ids))
                wheres[-1] = f"thread_id = %s AND run_id IN ({placeholders})"
                params = [str(thread_id)] + [str(r) for r in run_ids]

            rows = await conn.execute(
                f"SELECT * FROM runs WHERE {' AND '.join(wheres)}",
                params,
            )

            candidate_runs = [_row_to_dict(r) for r in rows]

            if filters:
                if thread_id:
                    thread_rows = await conn.execute(
                        "SELECT metadata FROM threads WHERE thread_id = %s",
                        (str(thread_id),),
                    )
                    if thread_rows:
                        if not _check_filter_match(thread_rows[0].get("metadata", {}), filters):
                            candidate_runs = []
                else:
                    # Batch fetch thread metadata to avoid N+1 queries
                    unique_thread_ids = {str(run.get("thread_id")) for run in candidate_runs if run.get("thread_id")}
                    if unique_thread_ids:
                        placeholders = ",".join(["%s"] * len(unique_thread_ids))
                        thread_rows = await conn.execute(
                            f"SELECT thread_id, metadata FROM threads WHERE thread_id IN ({placeholders})",
                            list(unique_thread_ids),
                        )
                        thread_metadata_map = {r["thread_id"]: r.get("metadata", {}) for r in thread_rows}

                        filtered_runs = []
                        for run in candidate_runs:
                            tid = run.get("thread_id")
                            if tid and _check_filter_match(thread_metadata_map.get(str(tid), {}), filters):
                                filtered_runs.append(run)
                        candidate_runs = filtered_runs
                    else:
                        candidate_runs = []

            if not candidate_runs:
                if assistant_id is not None:
                    return
                raise HTTPException(status_code=404, detail="No runs found to cancel.")

            # Cancel runs
            now = datetime.now(UTC)
            for run in candidate_runs:
                run_id = run["run_id"]
                run_thread_id = run["thread_id"]

                if run["status"] in ("pending", "running"):
                    if run["status"] == "pending":
                        # Update thread to idle if no other pending/running runs
                        other_rows = await conn.execute(
                            "SELECT COUNT(*) as cnt FROM runs WHERE thread_id = %s AND status IN ('pending', 'running') AND run_id != %s",
                            (str(run_thread_id), str(run_id)),
                        )
                        if other_rows and other_rows[0]["cnt"] == 0:
                            await conn.execute(
                                "UPDATE threads SET status = 'idle', updated_at = %s WHERE thread_id = %s",
                                (now, str(run_thread_id)),
                            )

                    if action == "rollback":
                        await Runs.delete(conn, run_id, thread_id=run_thread_id)
                    else:
                        await conn.execute(
                            "UPDATE runs SET status = 'interrupted', updated_at = %s WHERE run_id = %s",
                            (now, str(run_id)),
                        )

    @staticmethod
    async def search(
        conn,
        thread_id: UUID,
        *,
        limit: int = 10,
        offset: int = 0,
        status: str | None = None,
        select: list[str] | None = None,
        ctx: Auth.types.BaseAuthContext | None = None,
    ) -> AsyncIterator[dict]:
        """List all runs by thread."""
        thread_id = _ensure_uuid(thread_id)

        filters = await Runs.handle_event(
            ctx,
            "search",
            Auth.types.ThreadsSearch(thread_id=thread_id, metadata={}),
        )

        wheres = ["thread_id = %s"]
        params: list[Any] = [str(thread_id)]

        if status:
            wheres.append("status = %s")
            params.append(status)

        rows = await conn.execute(
            f"SELECT * FROM runs WHERE {' AND '.join(wheres)} ORDER BY created_at DESC LIMIT %s OFFSET %s",
            params + [limit, offset],
        )

        # Batch fetch thread metadata once to avoid N+1 in auth filtering
        thread_metadata = None
        if filters:
            thread_rows = await conn.execute(
                "SELECT metadata FROM threads WHERE thread_id = %s",
                (str(thread_id),),
            )
            thread_metadata = thread_rows[0].get("metadata", {}) if thread_rows else {}

        async def _yield():
            for row in rows:
                row_dict = _row_to_dict(row)
                if filters:
                    if not _check_filter_match(thread_metadata, filters):
                        continue
                if select:
                    yield {k: v for k, v in row_dict.items() if k in select}
                else:
                    yield row_dict

        return _yield()

    @staticmethod
    async def set_status(
        conn,
        run_id: UUID,
        status: str,
    ) -> None:
        """Set the status of a run (worker internal)."""
        run_id = _ensure_uuid(run_id)
        now = datetime.now(UTC)
        await conn.execute(
            "UPDATE runs SET status = %s, updated_at = %s WHERE run_id = %s",
            (status, now, str(run_id)),
        )

    @staticmethod
    async def next(
        wait: bool = True,
        limit: int = 1,
    ) -> AsyncIterator[tuple[dict, int]]:
        """Poll pending runs."""
        async with db_connect() as conn:
            while True:
                rows = await conn.execute(
                    "SELECT * FROM runs WHERE status = 'pending' AND created_at <= %s ORDER BY created_at ASC LIMIT %s FOR UPDATE SKIP LOCKED",
                    (datetime.now(UTC), limit),
                )
                for row in rows:
                    r = _row_to_dict(row)
                    now = datetime.now(UTC)
                    await conn.execute(
                        "UPDATE runs SET status = 'running', updated_at = %s WHERE run_id = %s",
                        (now, str(r["run_id"])),
                    )
                    attempt = r.get("attempt", 1)
                    yield r, attempt

                if not wait:
                    break
                await asyncio.sleep(1)

    @staticmethod
    async def sweep() -> None:
        """Mark stale runs as timed out."""
        async with db_connect() as conn:
            await conn.execute(
                "UPDATE runs SET status = 'timeout', updated_at = %s "
                "WHERE status = 'running' AND updated_at < NOW() - INTERVAL '%s seconds'",
                (datetime.now(UTC), STALE_RUN_TIMEOUT_SECS),
            )

    @asynccontextmanager
    @staticmethod
    async def enter(
        run_id: UUID,
        thread_id: UUID | None,
        loop: asyncio.AbstractEventLoop,
        resumable: bool,
    ) -> AsyncIterator[Any]:
        """Enter a run, listen for cancellation."""
        from langgraph_api.asyncio import SimpleTaskGroup, ValueEvent
        from langgraph_runtime_postgres_py.run_queue import get_redis

        run_id = _ensure_uuid(run_id)

        done = ValueEvent()
        redis = await get_redis()

        async def listen_for_cancel():
            pubsub = redis.pubsub()
            await pubsub.subscribe(f"run:{run_id}:control")
            while not done.is_set():
                message = await pubsub.get_message(timeout=1.0, ignore_subscribe_messages=True)
                if message:
                    payload = message.get("data", b"")
                    if isinstance(payload, bytes):
                        if payload == b"rollback":
                            from langgraph_api.errors import UserRollback
                            done.set(UserRollback())
                        elif payload == b"interrupt":
                            from langgraph_api.errors import UserInterrupt
                            done.set(UserInterrupt())
                        elif payload == b"done":
                            done.set()
                            break

        async with SimpleTaskGroup(cancel=True, taskgroup_name="Runs.enter") as tg:
            tg.create_task(listen_for_cancel())
            yield done

            # Send done message
            await redis.publish(f"run:{run_id}:stream", b"done")

    class Stream:
        """Run stream operations."""

        @staticmethod
        async def subscribe(
            run_id: UUID,
            thread_id: UUID | None = None,
        ) -> asyncio.Queue:
            """Subscribe to the run stream, returning a queue that receives messages."""
            from langgraph_runtime_inmem.inmem_stream import ContextQueue, get_stream_manager

            run_id = _ensure_uuid(run_id)
            stream_manager = get_stream_manager()
            queue = await stream_manager.add_queue(run_id, thread_id)
            return queue

        @staticmethod
        async def join(
            run_id: UUID,
            *,
            stream_channel: asyncio.Queue,
            thread_id: UUID,
            ignore_404: bool = False,
            cancel_on_disconnect: bool = False,
            stream_mode: str | list[str] | None = None,
            last_event_id: str | None = None,
            ctx: Auth.types.BaseAuthContext | None = None,
        ) -> AsyncIterator[tuple[bytes, bytes, bytes | None]]:
            """Stream the run output."""
            from langgraph_runtime_postgres_py.run_queue import get_redis

            await Runs.Stream.check_run_stream_auth(run_id, thread_id, ctx)

            redis = await get_redis()
            pubsub = redis.pubsub()
            await pubsub.subscribe(f"run:{run_id}:stream")

            try:
                async with db_connect() as conn:
                    while True:
                        message = await pubsub.get_message(timeout=0.5, ignore_subscribe_messages=True)
                        if message:
                            event = message.get("data", b"")
                            if isinstance(event, bytes):
                                if event == b"done":
                                    break
                                yield event, b"", None
                        else:
                            # Check if run still exists
                            rows = await conn.execute(
                                "SELECT status FROM runs WHERE run_id = %s",
                                (str(run_id),),
                            )
                            if not rows:
                                if ignore_404:
                                    break
                                yield b"error", b'{"detail": "Run not found"}', None
                                break
                            status = rows[0].get("status")
                            if status not in ("pending", "running"):
                                break
            except asyncio.CancelledError:
                if cancel_on_disconnect:
                    await Runs.cancel(None, [run_id], thread_id=thread_id)
                raise
            finally:
                await pubsub.unsubscribe(f"run:{run_id}:stream")

        @staticmethod
        async def check_run_stream_auth(
            run_id: UUID,
            thread_id: UUID,
            ctx: Auth.types.BaseAuthContext | None = None,
        ) -> None:
            """Check auth for run stream."""
            async with db_connect() as conn:
                filters = await Runs.handle_event(
                    ctx,
                    "read",
                    Auth.types.ThreadsRead(thread_id=thread_id),
                )
                if filters:
                    thread_rows = await conn.execute(
                        "SELECT metadata FROM threads WHERE thread_id = %s",
                        (str(thread_id),),
                    )
                    if not thread_rows:
                        raise HTTPException(status_code=404, detail="Thread not found")
                    if not _check_filter_match(thread_rows[0].get("metadata", {}), filters):
                        raise HTTPException(status_code=404, detail="Thread not found")

        @staticmethod
        async def publish(
            run_id: UUID | str,
            event: str,
            message: bytes,
            *,
            thread_id: UUID | str | None = None,
            resumable: bool = False,
        ) -> None:
            """Publish a message to the run stream."""
            from langgraph_runtime_postgres_py.run_queue import get_redis

            redis = await get_redis()
            await redis.publish(f"run:{run_id}:stream", message)


# ---- Crons ----

class Crons(Authenticated):
    resource = "crons"

    @staticmethod
    def _validate_cron_schedule_or_throw(schedule: str) -> None:
        """Validate cron schedule format."""
        import croniter as croniter_mod
        if not croniter_mod.croniter.is_valid(schedule):
            raise HTTPException(
                status_code=422,
                detail=f"Invalid cron schedule: '{schedule}'",
            )

    @staticmethod
    async def put(
        conn,
        *,
        payload: dict[str, Any],
        schedule: str,
        cron_id: UUID | None = None,
        thread_id: UUID | None = None,
        on_run_completed: Literal["delete", "keep"] | None = None,
        end_time: datetime | None = None,
        metadata: dict[str, Any] | None = None,
        enabled: bool = True,
        timezone: str | None = None,
        ctx: Auth.types.BaseAuthContext | None = None,
    ) -> AsyncIterator[dict]:
        """Create a cron."""
        from langgraph_api.graph import get_assistant_id
        from langgraph_api.utils import get_auth_ctx, next_cron_date, uuid7

        ctx = ctx or get_auth_ctx()
        user_id = ctx.user.identity if ctx else None
        cron_id = cron_id or uuid7()

        try:
            thread_id = UUID(str(thread_id)) if thread_id else None
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid thread ID {thread_id}")

        effective_on_run_completed = on_run_completed if thread_id is None else None
        if effective_on_run_completed is None:
            effective_on_run_completed = "delete"

        metadata = metadata or {}
        payload = payload or {}
        config = payload.get("config", {})
        if config is None:
            config = {}
            payload["config"] = config
        configurable = config.get("configurable", {})
        if configurable is None:
            configurable = {}
            config["configurable"] = configurable
        configurable["cron_id"] = str(cron_id)

        filters = await Crons.handle_event(
            ctx,
            "create",
            Auth.types.CronsCreate(
                payload=payload,
                schedule=schedule,
                cron_id=cron_id,
                thread_id=thread_id,
                user_id=user_id,
                end_time=end_time,
            ),
        )

        Crons._validate_cron_schedule_or_throw(schedule)

        assistant_id = get_assistant_id(payload.get("assistant_id", ""))
        payload["assistant_id"] = assistant_id

        # Validate assistant exists
        assistant_rows = await conn.execute(
            "SELECT * FROM assistants WHERE assistant_id = %s",
            (str(assistant_id),),
        )
        if not assistant_rows:
            raise HTTPException(status_code=404, detail=f"Assistant '{assistant_id}' not found")

        # Check existing cron
        existing_rows = await conn.execute(
            "SELECT * FROM crons WHERE cron_id = %s",
            (str(cron_id),),
        )
        if existing_rows:
            existing = _row_to_dict(existing_rows[0])
            if filters and not _check_filter_match(existing.get("metadata", {}), filters):
                return _empty_generator()
            async def _yield_existing():
                yield existing
            return _yield_existing()

        now = datetime.now(UTC)
        next_run = next_cron_date(schedule, now, timezone=timezone)

        await conn.execute(
            """INSERT INTO crons (cron_id, assistant_id, thread_id, user_id, schedule, timezone, payload, next_run_date, metadata, on_run_completed, enabled, created_at, updated_at, end_time)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (str(cron_id), str(assistant_id), str(thread_id) if thread_id else None,
             user_id, schedule, timezone, json.dumps(payload), next_run,
             json.dumps(metadata), effective_on_run_completed, enabled, now, now, end_time),
        )

        new_cron = {
            "cron_id": cron_id,
            "assistant_id": assistant_id,
            "thread_id": thread_id,
            "user_id": user_id,
            "schedule": schedule,
            "timezone": timezone,
            "payload": payload,
            "next_run_date": next_run,
            "metadata": metadata,
            "on_run_completed": effective_on_run_completed,
            "enabled": enabled,
            "created_at": now,
            "updated_at": now,
            "end_time": end_time,
        }

        async def _yield_new():
            yield new_cron
        return _yield_new()

    @staticmethod
    async def update(
        conn,
        *,
        cron_id: UUID,
        schedule: str | None = None,
        end_time: datetime | None = None,
        enabled: bool | None = None,
        on_run_completed: Literal["delete", "keep"] | None = None,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        timezone: str | None = None,
        ctx: Auth.types.BaseAuthContext | None = None,
    ) -> AsyncIterator[dict]:
        """Update a cron."""
        from langgraph_api.utils import get_auth_ctx, next_cron_date

        ctx = ctx or get_auth_ctx()
        cron_id = _ensure_uuid(cron_id)

        filters = await Crons.handle_event(
            ctx,
            "update",
            Auth.types.CronsUpdate(
                cron_id=cron_id,
                schedule=schedule,
                end_time=end_time,
                enabled=enabled,
                on_run_completed=on_run_completed,
                payload=payload,
            ),
        )

        existing_rows = await conn.execute(
            "SELECT * FROM crons WHERE cron_id = %s",
            (str(cron_id),),
        )
        if not existing_rows:
            raise HTTPException(status_code=404, detail=f"Cron '{cron_id}' not found")

        existing = _row_to_dict(existing_rows[0])
        if filters and not _check_filter_match(existing.get("metadata", {}), filters):
            raise HTTPException(status_code=404, detail=f"Cron '{cron_id}' not found")

        now = datetime.now(UTC)
        updated_fields = {}

        if schedule is not None:
            Crons._validate_cron_schedule_or_throw(schedule)
            updated_fields["schedule"] = schedule
            updated_fields["next_run_date"] = next_cron_date(schedule, now, timezone=timezone or existing.get("timezone"))
        elif timezone is not None:
            updated_fields["next_run_date"] = next_cron_date(existing["schedule"], now, timezone=timezone)

        if timezone is not None:
            updated_fields["timezone"] = timezone

        if end_time is not None:
            updated_fields["end_time"] = end_time

        if enabled is not None:
            updated_fields["enabled"] = enabled

        if on_run_completed is not None:
            updated_fields["on_run_completed"] = on_run_completed

        if metadata is not None:
            updated_fields["metadata"] = {**existing.get("metadata", {}), **metadata}

        if payload is not None:
            existing_payload = existing.get("payload", {})
            merged_payload = {**existing_payload, **payload}
            merged_payload["assistant_id"] = existing_payload.get("assistant_id", merged_payload.get("assistant_id"))
            merged_config = merged_payload.get("config", {})
            merged_configurable = merged_config.get("configurable", {})
            merged_configurable["cron_id"] = str(cron_id)
            merged_config["configurable"] = merged_configurable
            merged_payload["config"] = merged_config
            updated_fields["payload"] = merged_payload

        updated_fields["updated_at"] = now

        # Build update query
        sets = []
        params = []
        for key, value in updated_fields.items():
            if key in ("metadata", "payload"):
                sets.append(f"{key} = %s")
                params.append(json.dumps(value))
            elif isinstance(value, datetime):
                sets.append(f"{key} = %s")
                params.append(value)
            else:
                sets.append(f"{key} = %s")
                params.append(value)

        params.append(str(cron_id))
        await conn.execute(
            f"UPDATE crons SET {', '.join(sets)} WHERE cron_id = %s",
            params,
        )

        updated = {**existing, **updated_fields}

        async def _yield_updated():
            yield updated
        return _yield_updated()

    @staticmethod
    async def get(
        conn,
        cron_id: UUID | str,
        ctx: Auth.types.BaseAuthContext | None = None,
    ) -> AsyncIterator[dict]:
        """Get a cron by ID."""
        cron_id = _ensure_uuid(cron_id)
        filters = await Crons.handle_event(
            ctx,
            "read",
            Auth.types.CronsRead(cron_id=cron_id),
        )

        async def _yield_result():
            rows = await conn.execute(
                "SELECT * FROM crons WHERE cron_id = %s",
                (str(cron_id),),
            )
            if rows:
                row_dict = _row_to_dict(rows[0])
                if not filters or _check_filter_match(row_dict.get("metadata", {}), filters):
                    yield copy.deepcopy(row_dict)

        return _yield_result()

    @staticmethod
    async def delete(
        conn,
        cron_id: UUID,
        ctx: Auth.types.BaseAuthContext | None = None,
    ) -> AsyncIterator[UUID]:
        """Delete a cron by ID."""
        cron_id = _ensure_uuid(cron_id)
        filters = await Crons.handle_event(
            ctx,
            "delete",
            Auth.types.CronsDelete(cron_id=cron_id),
        )

        existing_rows = await conn.execute(
            "SELECT * FROM crons WHERE cron_id = %s",
            (str(cron_id),),
        )
        if existing_rows:
            existing = _row_to_dict(existing_rows[0])
            if not filters or _check_filter_match(existing.get("metadata", {}), filters):
                await conn.execute(
                    "DELETE FROM crons WHERE cron_id = %s",
                    (str(cron_id),),
                )

                async def _yield_deleted():
                    yield cron_id
                return _yield_deleted()

        return _empty_generator()

    @staticmethod
    async def next(
        conn,
        ctx: Auth.types.BaseAuthContext | None = None,
    ) -> AsyncIterator[dict]:
        """Get crons that need to run."""
        now = datetime.now(UTC)
        rows = await conn.execute(
            """SELECT * FROM crons
               WHERE enabled = true
               AND (end_time IS NULL OR end_time > %s)
               AND next_run_date <= %s
               ORDER BY next_run_date ASC""",
            (now, now),
        )

        for row in rows:
            row_dict = _row_to_dict(row)
            yield {**row_dict, "now": now}

    @staticmethod
    async def set_next_run_date(
        conn,
        cron_id: UUID,
        next_run_date: datetime,
        ctx: Auth.types.BaseAuthContext | None = None,
    ) -> None:
        """Set the next run date for a cron."""
        cron_id = _ensure_uuid(cron_id)
        await conn.execute(
            "UPDATE crons SET next_run_date = %s, updated_at = %s WHERE cron_id = %s",
            (next_run_date, datetime.now(UTC), str(cron_id)),
        )

    @staticmethod
    async def search(
        conn,
        *,
        assistant_id: UUID | None = None,
        thread_id: UUID | None = None,
        enabled: bool | None = None,
        limit: int = 10,
        offset: int = 0,
        select: list[str] | None = None,
        ctx: Auth.types.BaseAuthContext | None = None,
        sort_by: str | None = None,
        sort_order: Literal["asc", "desc"] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[AsyncIterator[dict], int | None]:
        """Search crons with pagination."""
        filters = await Crons.handle_event(
            ctx,
            "search",
            {
                "assistant_id": str(assistant_id) if assistant_id else None,
                "thread_id": str(thread_id) if thread_id else None,
                "limit": limit,
                "offset": offset,
                "metadata": metadata or {},
            },
        )

        wheres = ["1=1"]
        params: list[Any] = []

        if assistant_id:
            wheres.append("assistant_id = %s")
            params.append(str(assistant_id))

        if thread_id:
            wheres.append("thread_id = %s")
            params.append(str(thread_id))

        if enabled is not None:
            wheres.append("enabled = %s")
            params.append(enabled)

        if metadata:
            wheres.append("metadata @> %s")
            params.append(json.dumps(metadata))

        # Sorting
        sort_by_lower = sort_by.lower() if sort_by else None
        order_clause = "ORDER BY created_at DESC"
        if sort_by_lower in ("cron_id", "assistant_id", "thread_id", "next_run_date", "end_time", "created_at", "updated_at"):
            direction = "ASC" if sort_order and sort_order.upper() == "ASC" else "DESC"
            order_clause = f"ORDER BY {sort_by_lower} {direction}"

        rows = await conn.execute(
            f"SELECT * FROM crons WHERE {' AND '.join(wheres)} {order_clause} LIMIT %s OFFSET %s",
            params + [limit + 1, offset],
        )

        has_more = len(rows) > limit
        cursor = offset + limit if has_more else None

        async def _yield():
            for row in rows[:limit]:
                row_dict = _row_to_dict(row)
                if filters and not _check_filter_match(row_dict.get("metadata", {}), filters):
                    continue
                if select:
                    yield {k: v for k, v in row_dict.items() if k in select}
                else:
                    yield row_dict

        return _yield(), cursor

    @staticmethod
    async def count(
        conn,
        *,
        assistant_id: UUID | None = None,
        thread_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        ctx: Auth.types.BaseAuthContext | None = None,
    ) -> int:
        """Get count of crons."""
        filters = await Crons.handle_event(
            ctx,
            "search",
            {
                "assistant_id": str(assistant_id) if assistant_id else None,
                "thread_id": str(thread_id) if thread_id else None,
                "limit": 0,
                "offset": 0,
                "metadata": metadata or {},
            },
        )

        wheres = ["1=1"]
        params: list[Any] = []

        if assistant_id:
            wheres.append("assistant_id = %s")
            params.append(str(assistant_id))

        if thread_id:
            wheres.append("thread_id = %s")
            params.append(str(thread_id))

        if metadata:
            wheres.append("metadata @> %s")
            params.append(json.dumps(metadata))

        rows = await conn.execute(
            f"SELECT COUNT(*) as cnt FROM crons WHERE {' AND '.join(wheres)}",
            params,
        )
        total = rows[0]["cnt"] if rows else 0

        if filters:
            all_rows = await conn.execute(
                f"SELECT * FROM crons WHERE {' AND '.join(wheres)}",
                params,
            )
            total = sum(1 for r in all_rows if _check_filter_match(_row_to_dict(r).get("metadata", {}), filters))

        return total


# ---- RunEvents ----

class RunEvents:
    """Run event operations."""

    @staticmethod
    async def create(
        conn,
        *,
        run_id: UUID | str,
        span_id: UUID | str,
        event: str,
        name: str = "",
        tags: list[str] | None = None,
        data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        """Create a run event."""
        run_id = _ensure_uuid(run_id)
        span_id = _ensure_uuid(span_id)
        tags = tags or []
        data = data or {}
        metadata = metadata or {}

        now = datetime.now(UTC)
        rows = await conn.execute(
            """INSERT INTO run_events (run_id, span_id, event, name, tags, data, metadata, received_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
            (str(run_id), str(span_id), event, name, json.dumps(tags),
             json.dumps(data), json.dumps(metadata), now),
        )
        return _row_to_dict(rows[0]) if rows else {}

    @staticmethod
    async def search(
        conn,
        *,
        run_id: UUID | str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """Search run events."""
        run_id = _ensure_uuid(run_id)
        rows = await conn.execute(
            "SELECT * FROM run_events WHERE run_id = %s ORDER BY received_at ASC LIMIT %s OFFSET %s",
            (str(run_id), limit, offset),
        )
        return [_row_to_dict(r) for r in rows]


__all__ = [
    "Assistants",
    "Threads",
    "Runs",
    "Crons",
    "RunEvents",
    "Authenticated",
]
